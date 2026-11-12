"""
ironCrawler/webscraping/live_refresh.py

Keeps athlete data current for competitions that are happening right now.

Starting Chrome costs far more than loading a competition page, so instead of
one driver per scrape (see scrape_athlete_data.py) the live refresh keeps a
small pool of drivers open between passes and shares the live competitions
across them.

Behaviour:
  - A competition is live while its date is "today" anywhere in the world
  - Only competitions an admin has selected (Competition.scrape_enabled) are refreshed
  - Drivers scrape in parallel worker threads; all DB writes happen serially
  - A competition whose export is identical to the last one saved is not rewritten
  - A pass stops taking new competitions once its time budget is spent; the
    ones it did not reach are scraped first on the next pass
"""

import logging
import math
import queue
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone

from ..models import Competition
from .create_selenium_driver import create_webdriver
from .scrape_athlete_data import save_athletes_to_db, scrape_athletes_with_driver

logger = logging.getLogger(__name__)

# Each worker is a full Chrome instance kept open between passes — keep this low to avoid OOM.
MAX_LIVE_WORKERS = 4
# a reused driver scrapes a competition in ~2s, so this leaves plenty of headroom per pass
COMPETITIONS_PER_WORKER = 12
# stop starting new scrapes after this long so a pass finishes inside the 1 minute interval
PASS_BUDGET_SECONDS = 50
PAGE_LOAD_TIMEOUT_SECONDS = 30
# long-lived Chrome instances grow over time, so each one is replaced after this many scrapes
MAX_SCRAPES_PER_DRIVER = 300
# consecutive failed passes before a competition is logged as an error
FAILURE_ALERT_THRESHOLD = 3

####################################### HELPER FUNCTIONS ############################################

def live_competition_dates(now: datetime | None = None) -> list[date]:
    """Returns every calendar date that is "today" somewhere in the world right now.

    Competitions are stored with a date but no time zone, so a competition is
    treated as live while any time zone (UTC-12 to UTC+14) is still on its date.

    Args:
        now (datetime): aware datetime to evaluate. Defaults to the current time.

    Returns:
        list[date]: two or three consecutive dates
    """
    now = (now or timezone.now()).astimezone(dt_timezone.utc)
    first = (now - timedelta(hours=12)).date()
    last = (now + timedelta(hours=14)).date()
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]

class _LiveDriver:
    """One long-lived Chrome instance and its private download directory."""

    def __init__(self):
        self.download_dir = tempfile.mkdtemp(prefix="lc_live_")
        try:
            self.driver = create_webdriver(self.download_dir)
            self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)
        except Exception:
            shutil.rmtree(self.download_dir, ignore_errors=True)
            raise
        self.scrapes = 0

    def close(self):
        try:
            self.driver.quit()
        except Exception as e:
            logger.debug("Ignoring error while closing live driver: %s", e)
        shutil.rmtree(self.download_dir, ignore_errors=True)

####################################### DRIVER POOL ############################################

class LiveScraperPool:
    """Pool of long-lived drivers that scrapes a batch of competitions in parallel.

    Workers only do network/browser work — no DB access. Not safe to call
    scrape() from two threads at once.
    """

    def __init__(self, max_workers: int = MAX_LIVE_WORKERS):
        self.max_workers = max_workers
        self._drivers: list[_LiveDriver] = []

    def _worker(self, live_driver, work: queue.SimpleQueue, deadline: float) -> tuple:
        """Scrapes competitions from the queue until it is empty or the deadline passes."""
        results = []
        while time.monotonic() < deadline:
            try:
                competition = work.get_nowait()
            except queue.Empty:
                break

            try:
                if live_driver is None:
                    live_driver = _LiveDriver()
                digest, athletes_data = scrape_athletes_with_driver(
                    live_driver.driver, competition, live_driver.download_dir)
                live_driver.scrapes += 1
                results.append((competition, digest, athletes_data, None))
            except Exception as e:
                # a driver that failed may still be mid-download, so it is never reused:
                # a late file must not be read as the next competition's export
                if live_driver is not None:
                    live_driver.close()
                    live_driver = None
                results.append((competition, None, [], f"{type(e).__name__}: {e}"))
                continue

            if live_driver.scrapes >= MAX_SCRAPES_PER_DRIVER:
                live_driver.close()
                live_driver = None

        return live_driver, results

    def scrape(self, competitions: list, deadline: float) -> tuple[list, list]:
        """Scrapes athletes for the given competitions, in order, until the deadline.

        Args:
            competitions (list): competitions to scrape, most overdue first
            deadline (float): time.monotonic() value after which no new scrape starts

        Returns:
            (results, not_reached) where results is a list of
            (competition, digest, athletes_data, error) and not_reached is the
            competitions the pass ran out of time for.
        """
        if not competitions:
            return [], []

        n_workers = min(self.max_workers, math.ceil(len(competitions) / COMPETITIONS_PER_WORKER))
        work = queue.SimpleQueue()
        for competition in competitions:
            work.put(competition)

        # hand each worker an open driver if there is one, and close any surplus
        drivers, self._drivers = self._drivers[:n_workers], self._drivers[n_workers:]
        self.close()
        drivers += [None] * (n_workers - len(drivers))

        results = []
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = [pool.submit(self._worker, live_driver, work, deadline) for live_driver in drivers]
            for future in futures:
                live_driver, worker_results = future.result()
                if live_driver is not None:
                    self._drivers.append(live_driver)
                results.extend(worker_results)

        not_reached = []
        while not work.empty():
            not_reached.append(work.get_nowait())
        return results, not_reached

    def close(self):
        """Closes every open driver. The pool can still be used afterwards."""
        for live_driver in self._drivers:
            live_driver.close()
        self._drivers = []

####################################### LIVE REFRESH ############################################

class LiveRefresher:
    """Runs live refresh passes and remembers what each competition last looked like."""

    def __init__(self, pool: LiveScraperPool = None):
        self.pool = pool or LiveScraperPool()
        self._saved_digest: dict[int, str] = {}     # comp_id -> hash of the last export saved
        self._last_scraped: dict[int, float] = {}   # comp_id -> time.monotonic() of last good scrape
        self._failures: dict[int, int] = {}         # comp_id -> consecutive failed passes

    def _record_failure(self, competition: Competition, error: str):
        failures = self._failures.get(competition.pk, 0) + 1
        self._failures[competition.pk] = failures
        if failures == FAILURE_ALERT_THRESHOLD:
            logger.error("Live refresh has failed %d times in a row for %s | url=%s | %s",
                         failures, competition, competition.comp_url, error)
        else:
            logger.warning("Live refresh failed for %s (%d in a row): %s", competition, failures, error)

    def _forget_finished(self, live_ids: set):
        """Drops remembered state for competitions that are no longer live."""
        for state in (self._saved_digest, self._last_scraped, self._failures):
            for comp_id in set(state) - live_ids:
                del state[comp_id]

    def refresh(self) -> dict:
        """Runs one pass: scrapes every live competition and saves the ones that changed.

        Returns:
            dict: counts for the pass — live, updated, unchanged, failed, not_reached, seconds
        """
        started = time.monotonic()
        competitions = list(Competition.objects.filter(
            scrape_enabled=True, comp_date__in=live_competition_dates()))
        self._forget_finished({competition.pk for competition in competitions})

        summary = {'live': len(competitions), 'updated': 0, 'unchanged': 0,
                   'failed': 0, 'not_reached': 0, 'seconds': 0.0}
        if not competitions:
            self.pool.close()
            return summary

        # most overdue first, so competitions a slow pass did not reach go to the front
        competitions.sort(key=lambda competition: self._last_scraped.get(competition.pk, 0))
        results, not_reached = self.pool.scrape(competitions, started + PASS_BUDGET_SECONDS)
        summary['not_reached'] = len(not_reached)

        for competition, digest, athletes_data, error in results:
            if error:
                summary['failed'] += 1
                self._record_failure(competition, error)
                continue

            self._last_scraped[competition.pk] = time.monotonic()
            self._failures.pop(competition.pk, None)

            if self._saved_digest.get(competition.pk) == digest:
                summary['unchanged'] += 1
                continue

            try:
                save_athletes_to_db(competition, athletes_data)
            except Exception as e:
                # e.g. the database was locked by the full scrape, or the competition
                # was removed mid-pass; the digest is not stored, so the next pass retries
                summary['failed'] += 1
                logger.warning("Live refresh could not save %s: %s: %s", competition, type(e).__name__, e)
                continue

            self._saved_digest[competition.pk] = digest
            summary['updated'] += 1
            logger.info("  [live updated] %s — %d athletes", competition, len(athletes_data))

        summary['seconds'] = round(time.monotonic() - started, 1)
        return summary

    def close(self):
        self.pool.close()


# single shared instance: the scheduler runs one live refresh pass at a time
live_refresher = LiveRefresher()
