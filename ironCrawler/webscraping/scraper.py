"""
ironCrawler/webscraping/scraper.py

Provides scrape_and_load() — the single entry point used by the scheduler
and management commands to sync liftingcast.com competitions with the DB.

Behaviour:
  - Creates competitions that don't exist yet
  - Removes competitions that have disappeared from the site
  - Scrapes and saves the athletes of every competition an admin has selected
  - Returns (created_count, skipped_count, athletes_count, failed_competitions)
    so callers can log the result
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from ironCrawler.models import Competition
from ironCrawler.webscraping.live_refresh import live_competition_dates
from ironCrawler.webscraping.scrape_athlete_data import (
    save_athletes_to_db,
    scrape_athletes_only,
)
from ironCrawler.webscraping.scrape_competition_data import get_competition_data

# Each worker is a full Chrome instance — keep this low to avoid OOM.
MAX_SCRAPE_WORKERS = 4

logger = logging.getLogger(__name__)


def scrape_and_load(skip_live: bool = False) -> tuple[int, int, int, list[str]]:
    """
    Scrapes liftingcast.com for upcoming competitions and syncs them with
    the Competition table. Then scrapes athletes for the competitions an admin
    has selected (Competition.scrape_enabled).

    - New competitions are created, not selected for scraping.
    - Competitions no longer returned by the scraper are deleted.
    - Athletes are scraped and saved for the selected competitions.
    - Competitions whose athlete scrape fails are collected and returned
      so callers can log/alert without blocking the rest of the run.

    Args:
        skip_live (bool): leave out the athlete scrape for competitions that have
            begun (see live_competition_dates). The scheduler sets this because
            its live refresh already scrapes those competitions every minute.

    Returns:
        (created_count, skipped_count, athletes_count, failed_competitions)
    """
    # ── Step 1: fetch competition list ────────────────────────────────────
    logger.info("Step 1/3 — Fetching competition list from liftingcast.com...")
    live_competitions = get_competition_data()

    if not live_competitions:
        logger.warning("Scraper returned no competitions — skipping DB sync to avoid wiping data.")
        return 0, 0, 0, []

    logger.info("Step 1/3 complete — found %d competitions on liftingcast.com", len(live_competitions))

    # ── Step 2: sync competitions with the DB ─────────────────────────────
    logger.info("Step 2/3 — Syncing competition list with database...")
    created  = 0
    skipped  = 0
    live_keys = set()   # (name, date) pairs seen in this scrape run

    for comp in live_competitions:
        name = comp['name']
        date = comp['date']
        link = comp['link']

        _, was_created = Competition.objects.get_or_create(
            comp_name=name,
            comp_date=date,
            defaults={'comp_url': link},
        )

        live_keys.add((name, date))

        if was_created:
            created += 1
            logger.info("  [new] %s (%s)", name, date)
        else:
            skipped += 1
            logger.debug("  [exists] %s (%s)", name, date)

    # More precise: only delete if BOTH name AND date are absent
    stale_qs = Competition.objects.all()
    for comp_obj in stale_qs:
        if (comp_obj.comp_name, str(comp_obj.comp_date)) not in live_keys:
            logger.info("  [removed stale] %s (%s)", comp_obj.comp_name, comp_obj.comp_date)
            comp_obj.delete()

    logger.info("Step 2/3 complete — competitions created: %d, skipped: %d", created, skipped)

    # ── Step 3: scrape athletes (parallel scrape, serial DB write) ────────
    # Workers only do network/browser work — no DB access — to avoid SQLite
    # "database is locked" errors from concurrent writes.
    competitions = Competition.objects.filter(scrape_enabled=True)
    logger.info("Step 3/3 — %d of %d competitions are selected for scraping",
                competitions.count(), Competition.objects.count())
    if skip_live:
        live = competitions.filter(comp_date__in=live_competition_dates())
        logger.info("Step 3/3 — leaving %d live competition(s) to the live refresh", live.count())
        competitions = competitions.exclude(pk__in=live)
    competitions = list(competitions)
    n_workers = min(MAX_SCRAPE_WORKERS, len(competitions)) if competitions else 1
    logger.info("Step 3/3 — Scraping athletes for %d competitions (%d parallel workers)...", len(competitions), n_workers)

    athletes_total = 0
    failed_comps: list[str] = []
    scraped_results: list[tuple] = []

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(scrape_athletes_only, comp): comp for comp in competitions}
        for future in as_completed(futures):
            comp, athletes_data, error = future.result()
            if error:
                failed_comps.append(str(comp))
                logger.error("  [failed after retry] %s — %s", comp, error)
            else:
                scraped_results.append((comp, athletes_data))
                logger.info("  [scraped] %s — %d athletes found", comp, len(athletes_data))

    for comp, athletes_data in scraped_results:
        save_athletes_to_db(comp, athletes_data)
        athletes_total += len(athletes_data)
        logger.info("  [saved] %s — %d athletes written to DB", comp, len(athletes_data))

    if failed_comps:
        logger.error(
            "Step 3/3 complete with %d failure(s) after retry: %s",
            len(failed_comps),
            ", ".join(failed_comps),
        )
    else:
        logger.info("Step 3/3 complete — all competitions scraped successfully")

    logger.info(
        "Full sync complete — competitions created: %d, skipped: %d, athletes: %d, failed: %d",
        created, skipped, athletes_total, len(failed_comps),
    )
    return created, skipped, athletes_total, failed_comps