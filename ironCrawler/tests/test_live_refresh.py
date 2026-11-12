import time
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from ironCrawler.models import Competition
from ironCrawler.webscraping import live_refresh
from ironCrawler.webscraping.live_refresh import (
    COMPETITIONS_PER_WORKER,
    MAX_LIVE_WORKERS,
    LiveRefresher,
    LiveScraperPool,
    live_competition_dates,
)

from .helpers import athlete_row, make_competition


class LiveCompetitionDatesTests(SimpleTestCase):
    def _dates(self, *args):
        now = datetime(*args, tzinfo=dt_timezone.utc)
        return [d.isoformat() for d in live_competition_dates(now)]

    def test_us_evening_still_counts_the_local_date(self):
        # 7pm Saturday in US Central is already 01:00 Sunday UTC
        self.assertIn('2026-11-14', self._dates(2026, 11, 15, 1, 0))

    def test_australian_morning_counts_before_utc_reaches_the_date(self):
        # 8am Saturday in Sydney is 21:00 Friday UTC
        self.assertIn('2026-11-14', self._dates(2026, 11, 13, 21, 0))

    def test_dates_far_from_today_are_not_live(self):
        dates = self._dates(2026, 11, 14, 12, 0)
        self.assertEqual(dates, ['2026-11-14', '2026-11-15'])


class _FakeLiveDriver:
    """Stands in for _LiveDriver so the pool can be tested without starting Chrome."""

    created = []

    def __init__(self):
        self.driver = object()
        self.download_dir = 'unused'
        self.scrapes = 0
        self.closed = False
        _FakeLiveDriver.created.append(self)

    def close(self):
        self.closed = True


class LiveScraperPoolTests(SimpleTestCase):
    def setUp(self):
        _FakeLiveDriver.created = []
        self.failing = set()      # competition pks whose scrape raises
        self.used = {}            # competition pk -> the driver that scraped it

        for name, replacement in (('_LiveDriver', _FakeLiveDriver),
                                  ('scrape_athletes_with_driver', self._scrape)):
            patcher = mock.patch.object(live_refresh, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.pool = LiveScraperPool()

    def _scrape(self, driver, competition, download_dir):
        self.used[competition.pk] = driver
        if competition.pk in self.failing:
            raise TimeoutError('slow')
        return f'digest-{competition.pk}', [athlete_row('ana')]

    def _comps(self, count: int) -> list:
        return [SimpleNamespace(pk=i, comp_url=f'https://liftingcast.com/meets/{i}/results')
                for i in range(count)]

    def _scrape_all(self, comps):
        return self.pool.scrape(comps, time.monotonic() + 30)

    def _open_drivers(self):
        return [d for d in _FakeLiveDriver.created if not d.closed]

    def test_every_competition_is_scraped(self):
        results, not_reached = self._scrape_all(self._comps(30))

        self.assertEqual(sorted(c.pk for c, _, _, _ in results), list(range(30)))
        self.assertEqual(not_reached, [])
        self.assertTrue(all(error is None and digest == f'digest-{c.pk}'
                            for c, digest, _, error in results))

    def test_no_competitions_starts_no_drivers(self):
        self.assertEqual(self._scrape_all([]), ([], []))
        self.assertEqual(_FakeLiveDriver.created, [])

    def test_worker_count_grows_with_the_workload_up_to_the_limit(self):
        self._scrape_all(self._comps(COMPETITIONS_PER_WORKER * MAX_LIVE_WORKERS * 3))

        self.assertLessEqual(len(_FakeLiveDriver.created), MAX_LIVE_WORKERS)

    def test_small_workload_uses_one_driver(self):
        self._scrape_all(self._comps(COMPETITIONS_PER_WORKER))

        self.assertEqual(len(_FakeLiveDriver.created), 1)

    def test_drivers_are_reused_on_the_next_pass(self):
        comps = self._comps(COMPETITIONS_PER_WORKER)
        self._scrape_all(comps)
        self._scrape_all(comps)

        self.assertEqual(len(_FakeLiveDriver.created), 1)
        self.assertEqual(_FakeLiveDriver.created[0].scrapes, 2 * len(comps))

    def test_surplus_drivers_are_closed_when_the_workload_shrinks(self):
        self.pool._drivers = [_FakeLiveDriver() for _ in range(3)]
        self._scrape_all(self._comps(2))

        self.assertEqual(len(self._open_drivers()), 1)

    def test_failed_scrape_is_reported_and_its_driver_is_never_reused(self):
        self.failing = {3}
        results, _ = self._scrape_all(self._comps(6))

        errors = {c.pk: error for c, _, _, error in results if error}
        self.assertEqual(errors, {3: 'TimeoutError: slow'})
        failed_driver = next(d for d in _FakeLiveDriver.created if d.driver is self.used[3])
        self.assertTrue(failed_driver.closed)
        self.assertIsNot(self.used[4], self.used[3])
        self.assertEqual(len(results), 6)

    def test_driver_is_replaced_after_its_scrape_limit(self):
        with mock.patch.object(live_refresh, 'MAX_SCRAPES_PER_DRIVER', 2):
            self._scrape_all(self._comps(5))

        self.assertEqual(len(_FakeLiveDriver.created), 3)
        self.assertEqual(len(self._open_drivers()), 1)

    def test_nothing_is_started_after_the_deadline(self):
        comps = self._comps(4)
        results, not_reached = self.pool.scrape(comps, time.monotonic() - 1)

        self.assertEqual(results, [])
        self.assertEqual(not_reached, comps)

    def test_close_shuts_every_driver(self):
        self._scrape_all(self._comps(COMPETITIONS_PER_WORKER * 2))
        self.pool.close()

        self.assertEqual(self._open_drivers(), [])
        self.assertEqual(self.pool._drivers, [])


class _FakePool:
    """Stands in for LiveScraperPool: returns canned exports instead of driving Chrome."""

    def __init__(self):
        self.exports = {}        # comp pk -> (digest, athletes_data) or an error string
        self.reach = None        # limit on how many competitions a pass gets to
        self.seen = []           # order competitions were handed over in, per pass
        self.closed = False

    def scrape(self, competitions, deadline):
        self.seen.append([c.pk for c in competitions])
        reached = competitions[:self.reach] if self.reach is not None else competitions
        results = []
        for comp in reached:
            export = self.exports[comp.pk]
            if isinstance(export, str):
                results.append((comp, None, [], export))
            else:
                results.append((comp, export[0], export[1], None))
        return results, competitions[len(reached):]

    def close(self):
        self.closed = True


class LiveRefresherTests(TestCase):
    def setUp(self):
        today = timezone.now().date()
        self.a = make_competition('a', today)
        self.b = make_competition('b', today)
        self.old = make_competition('old', today - timedelta(days=5))
        self.pool = _FakePool()
        self.pool.exports = {self.a.pk: ('a1', [athlete_row('ana')]), self.b.pk: ('b1', [athlete_row('bea')])}
        self.refresher = LiveRefresher(pool=self.pool)

    def test_only_live_competitions_are_scraped_and_saved(self):
        summary = self.refresher.refresh()

        self.assertEqual((summary['live'], summary['updated']), (2, 2))
        self.assertEqual(self.a.athletes.count(), 1)
        self.assertEqual(self.old.athletes.count(), 0)

    def test_live_competition_not_selected_for_scraping_is_left_alone(self):
        off = make_competition('off', timezone.now().date(), scrape_enabled=False)
        summary = self.refresher.refresh()

        self.assertEqual(summary['live'], 2)
        self.assertNotIn(off.pk, self.pool.seen[0])

    def test_unchanged_export_is_not_saved_again(self):
        self.refresher.refresh()
        with mock.patch.object(live_refresh, 'save_athletes_to_db') as save:
            summary = self.refresher.refresh()

        save.assert_not_called()
        self.assertEqual((summary['updated'], summary['unchanged']), (0, 2))

    def test_changed_export_is_saved(self):
        self.refresher.refresh()
        self.pool.exports[self.a.pk] = ('a2', [athlete_row('ana', total='300')])
        summary = self.refresher.refresh()

        self.assertEqual((summary['updated'], summary['unchanged']), (1, 1))
        self.assertEqual(self.a.athletes.get().total, 300)

    def test_withdrawn_athlete_is_removed_by_a_live_pass(self):
        self.pool.exports[self.a.pk] = ('a1', [athlete_row('ana'), athlete_row('cat')])
        self.refresher.refresh()
        self.pool.exports[self.a.pk] = ('a2', [athlete_row('ana')])
        self.refresher.refresh()

        self.assertEqual(list(self.a.athletes.values_list('athlete_name', flat=True)), ['ana'])

    def test_failed_scrape_keeps_existing_athletes(self):
        self.refresher.refresh()
        self.pool.exports[self.a.pk] = 'TimeoutError: CSV download did not complete in time.'
        summary = self.refresher.refresh()

        self.assertEqual(summary['failed'], 1)
        self.assertEqual(self.a.athletes.count(), 1)

    def test_failed_save_is_retried_on_the_next_pass(self):
        with mock.patch.object(live_refresh, 'save_athletes_to_db',
                               side_effect=RuntimeError('database is locked')):
            summary = self.refresher.refresh()
        self.assertEqual((summary['updated'], summary['failed']), (0, 2))

        summary = self.refresher.refresh()
        self.assertEqual(summary['updated'], 2)

    def test_competition_not_reached_goes_first_on_the_next_pass(self):
        self.pool.reach = 1
        summary = self.refresher.refresh()
        self.assertEqual(summary['not_reached'], 1)

        missed = self.pool.seen[0][1]
        self.refresher.refresh()
        self.assertEqual(self.pool.seen[1][0], missed)

    def test_state_is_dropped_once_a_competition_is_no_longer_live(self):
        self.refresher.refresh()
        Competition.objects.filter(pk=self.a.pk).delete()
        self.refresher.refresh()

        self.assertEqual(set(self.refresher._saved_digest), {self.b.pk})

    def test_drivers_are_closed_when_nothing_is_live(self):
        Competition.objects.filter(pk__in=[self.a.pk, self.b.pk]).delete()
        summary = self.refresher.refresh()

        self.assertEqual(summary['live'], 0)
        self.assertTrue(self.pool.closed)
