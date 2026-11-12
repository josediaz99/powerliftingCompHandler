from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from ironCrawler.models import Competition
from ironCrawler.webscraping import scraper
from ironCrawler.webscraping.scrape_athlete_data import save_athletes_to_db
from ironCrawler.webscraping.scraper import scrape_and_load

from .helpers import athlete_row, make_competition


def _listed(name: str, comp_date) -> dict:
    """A competition the way get_competition_data returns it."""
    return {'name': name, 'date': comp_date.isoformat(),
            'link': f'https://liftingcast.com/meets/{name}/results'}


class ScrapeAndLoadTests(TestCase):
    def setUp(self):
        self.today = timezone.now().date()
        self.later = self.today + timedelta(days=5)
        self.rosters = {}     # competition name -> athlete rows, or an error string
        self.scraped = []     # competition names handed to the athlete scraper

        for name, replacement in (('get_competition_data', self._listing),
                                  ('scrape_athletes_only', self._scrape_athletes)):
            patcher = mock.patch.object(scraper, name, side_effect=replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.listing = []

    def _listing(self):
        return self.listing

    def _scrape_athletes(self, competition):
        self.scraped.append(competition.comp_name)
        roster = self.rosters.get(competition.comp_name, [])
        if isinstance(roster, str):
            return competition, [], roster
        return competition, roster, None

    def _select(self, *names, comp_date=None):
        """Stores competitions an admin has already switched on for scraping."""
        for name in names:
            make_competition(name, comp_date or self.later)

    def test_new_competitions_are_stored_but_not_scraped_until_selected(self):
        self.listing = [_listed('a', self.later), _listed('b', self.later)]

        result = scrape_and_load()

        self.assertEqual(result, (2, 0, 0, []))
        self.assertEqual(self.scraped, [])
        self.assertFalse(Competition.objects.filter(scrape_enabled=True).exists())
        self.assertEqual(Competition.objects.get(comp_name='a').comp_url,
                         'https://liftingcast.com/meets/a/results')

    def test_only_selected_competitions_have_their_athletes_saved(self):
        self._select('a', 'b')
        make_competition('off', self.later, scrape_enabled=False)
        self.listing = [_listed('a', self.later), _listed('b', self.later), _listed('off', self.later)]
        self.rosters = {'a': [athlete_row('ana'), athlete_row('bea')], 'b': [athlete_row('cat')],
                        'off': [athlete_row('dee')]}

        result = scrape_and_load()

        self.assertEqual(result, (0, 3, 3, []))
        self.assertEqual(sorted(self.scraped), ['a', 'b'])
        self.assertEqual(Competition.objects.get(comp_name='a').athletes.count(), 2)
        self.assertEqual(Competition.objects.get(comp_name='off').athletes.count(), 0)

    def test_selection_survives_a_sync(self):
        self._select('a')
        self.listing = [_listed('a', self.later)]

        scrape_and_load()

        self.assertTrue(Competition.objects.get(comp_name='a').scrape_enabled)

    def test_competition_already_stored_is_kept_not_duplicated(self):
        existing = make_competition('a', self.later)
        self.listing = [_listed('a', self.later)]

        created, skipped, _, _ = scrape_and_load()

        self.assertEqual((created, skipped), (0, 1))
        self.assertEqual(list(Competition.objects.values_list('pk', flat=True)), [existing.pk])

    def test_competition_no_longer_listed_is_removed_with_its_athletes(self):
        gone = make_competition('gone', self.later)
        save_athletes_to_db(gone, [athlete_row('ana')])
        self.listing = [_listed('a', self.later)]

        scrape_and_load()

        self.assertEqual(list(Competition.objects.values_list('comp_name', flat=True)), ['a'])
        self.assertFalse(gone.athletes.exists())

    def test_empty_listing_does_not_wipe_the_database(self):
        make_competition('a', self.later)
        self.listing = []

        self.assertEqual(scrape_and_load(), (0, 0, 0, []))
        self.assertEqual(Competition.objects.count(), 1)
        self.assertEqual(self.scraped, [])

    def test_failed_athlete_scrape_is_reported_and_the_rest_are_saved(self):
        self._select('a', 'b')
        self.listing = [_listed('a', self.later), _listed('b', self.later)]
        self.rosters = {'a': 'TimeoutError: slow', 'b': [athlete_row('cat')]}

        _, _, athletes, failed = scrape_and_load()

        self.assertEqual(athletes, 1)
        self.assertEqual(failed, [str(Competition.objects.get(comp_name='a'))])

    def test_live_competitions_are_scraped_by_default(self):
        self._select('live', comp_date=self.today)
        self._select('upcoming')
        self.listing = [_listed('live', self.today), _listed('upcoming', self.later)]

        scrape_and_load()

        self.assertEqual(sorted(self.scraped), ['live', 'upcoming'])

    def test_skip_live_leaves_competitions_that_have_begun_to_the_live_refresh(self):
        self._select('live', comp_date=self.today)
        self._select('upcoming')
        self.listing = [_listed('live', self.today), _listed('upcoming', self.later)]

        _, skipped, _, _ = scrape_and_load(skip_live=True)

        self.assertEqual(skipped, 2)
        self.assertEqual(self.scraped, ['upcoming'])
