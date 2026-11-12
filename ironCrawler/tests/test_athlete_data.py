import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase

from ironCrawler.models import Athlete
from ironCrawler.webscraping import scrape_athlete_data
from ironCrawler.webscraping.scrape_athlete_data import (
    _athlete_data_to_dicts,
    _clean_athlete_csv,
    _to_best_lift,
    _to_float,
    _wait_for_new_csv,
    save_athletes_to_db,
    scrape_and_save_athletes,
    scrape_athletes_only,
    scrape_athletes_with_driver,
)

from .helpers import athlete_row, make_competition

# Same shape as a liftingcast awards-results export, cut down to the columns that matter:
# a BOM, every value quoted, failed lifts negative and referee decisions containing commas.
SAMPLE_CSV = (
    '﻿"Name","Gender","Raw/Equipped","Team","Awards Division","Body Weight (kg)","Weight Class",'
    '"Exact Age","Best Squat","Best Bench","Best Deadlift","Total","Dots Points","S1LRef"\n'
    '"Ana O\'Neil","FEMALE","RAW"," Iron Club ","Womens Open","62.9","63",'
    '"21","127.5","52.5","165","345","371.33","bad, yellow"\n'
    '"Bea Stone","FEMALE","RAW","","Womens Open",,"63",'
    '"19",,"-25",,"0","0",\n'
)


class TempDirMixin:
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="lc_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, name: str, content: str = SAMPLE_CSV) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        return path


class CleanAthleteCsvTests(TempDirMixin, SimpleTestCase):
    def test_header_is_lowercased_and_bom_is_dropped(self):
        header, _ = _clean_athlete_csv(self.write('meet.csv'))

        self.assertEqual(header[0], 'name')
        self.assertIn('awards division', header)

    def test_values_are_lowercased_trimmed_and_stripped_of_quotes(self):
        _, athletes = _clean_athlete_csv(self.write('meet.csv'))

        self.assertEqual(athletes[0][0], 'ana oneil')
        self.assertEqual(athletes[0][3], 'iron club')

    def test_comma_inside_a_referee_decision_stays_in_one_column(self):
        header, athletes = _clean_athlete_csv(self.write('meet.csv'))

        self.assertEqual(len(athletes[0]), len(header))
        self.assertEqual(athletes[0][-1], 'bad, yellow')

    def test_empty_file_gives_no_header_and_no_athletes(self):
        self.assertEqual(_clean_athlete_csv(self.write('empty.csv', '')), ([], []))

    def test_rows_become_dicts_keyed_by_header(self):
        athletes = _athlete_data_to_dicts(self.write('meet.csv'))

        self.assertEqual(len(athletes), 2)
        self.assertEqual(athletes[1]['name'], 'bea stone')
        self.assertEqual(athletes[1]['best bench'], '-25')


class NumberParsingTests(SimpleTestCase):
    def test_to_float_reads_numbers(self):
        self.assertEqual(_to_float('127.5'), 127.5)
        self.assertEqual(_to_float(' -200 '), -200)

    def test_to_float_treats_blank_dash_and_text_as_zero(self):
        for value in ('', '-', None, 'n/a'):
            self.assertEqual(_to_float(value), 0.0)

    def test_best_lift_with_every_attempt_failed_counts_as_zero(self):
        self.assertEqual(_to_best_lift('-25'), 0.0)
        self.assertEqual(_to_best_lift('52.5'), 52.5)


class SaveAthletesToDbTests(TempDirMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.comp = make_competition('test meet', '2026-11-14')
        self.other = make_competition('other meet', '2026-11-14')

    def _names(self, competition):
        return sorted(competition.athletes.values_list('athlete_name', flat=True))

    def test_csv_columns_are_mapped_to_athlete_fields(self):
        save_athletes_to_db(self.comp, _athlete_data_to_dicts(self.write('meet.csv')))

        ana = Athlete.objects.get(competition=self.comp, athlete_name='ana oneil')
        self.assertEqual(
            (ana.gender, ana.team, ana.division, ana.weight_class),
            ('female', 'iron club', 'womens open', '63'))
        self.assertEqual(
            (ana.body_weight, ana.best_squat, ana.best_bench, ana.best_deadlift, ana.total),
            (62.9, 127.5, 52.5, 165, 345))
        self.assertAlmostEqual(ana.dots_score, 371.33)

    def test_athlete_who_has_not_lifted_gets_zeros_and_no_body_weight(self):
        save_athletes_to_db(self.comp, _athlete_data_to_dicts(self.write('meet.csv')))

        bea = Athlete.objects.get(competition=self.comp, athlete_name='bea stone')
        self.assertIsNone(bea.body_weight)
        self.assertIsNone(bea.dots_score)
        self.assertEqual((bea.best_squat, bea.best_bench, bea.total), (0, 0, 0))

    def test_withdrawn_athlete_is_removed(self):
        save_athletes_to_db(self.comp, [athlete_row('ana'), athlete_row('bea'), athlete_row('cat')])
        removed = save_athletes_to_db(self.comp, [athlete_row('ana'), athlete_row('cat')])

        self.assertEqual(removed, 1)
        self.assertEqual(self._names(self.comp), ['ana', 'cat'])

    def test_remaining_athletes_keep_their_id_and_update(self):
        save_athletes_to_db(self.comp, [athlete_row('ana'), athlete_row('bea')])
        ana_id = Athlete.objects.get(competition=self.comp, athlete_name='ana').id
        save_athletes_to_db(self.comp, [athlete_row('ana', total='300')])

        ana = Athlete.objects.get(competition=self.comp, athlete_name='ana')
        self.assertEqual(ana.id, ana_id)
        self.assertEqual(ana.total, 300)

    def test_other_competitions_are_untouched(self):
        save_athletes_to_db(self.other, [athlete_row('bea'), athlete_row('dee')])
        save_athletes_to_db(self.comp, [athlete_row('ana'), athlete_row('bea')])
        save_athletes_to_db(self.comp, [athlete_row('ana')])

        self.assertEqual(self._names(self.other), ['bea', 'dee'])

    def test_empty_scrape_removes_nobody(self):
        save_athletes_to_db(self.comp, [athlete_row('ana'), athlete_row('bea')])
        removed = save_athletes_to_db(self.comp, [])

        self.assertEqual(removed, 0)
        self.assertEqual(self._names(self.comp), ['ana', 'bea'])


class WaitForNewCsvTests(TempDirMixin, SimpleTestCase):
    def test_returns_the_csv_that_was_not_there_before(self):
        old = self.write('old.csv')
        new = self.write('new.csv')

        self.assertEqual(_wait_for_new_csv(self.tmp, {old}, timeout=2), new)

    def test_unrelated_partial_download_does_not_hold_up_the_csv(self):
        self.write('downloads.htm.crdownload', '')
        new = self.write('meet.csv')

        self.assertEqual(_wait_for_new_csv(self.tmp, set(), timeout=2), new)

    def test_times_out_while_the_csv_is_still_downloading(self):
        self.write('meet.csv.crdownload', '')

        with self.assertRaises(TimeoutError):
            _wait_for_new_csv(self.tmp, set(), timeout=1)

    def test_times_out_when_no_new_csv_arrives(self):
        old = self.write('old.csv')

        with self.assertRaises(TimeoutError):
            _wait_for_new_csv(self.tmp, {old}, timeout=1)


@mock.patch.object(scrape_athlete_data, 'RETRY_DELAY_SECONDS', 0)
class ScrapeAthletesOnlyTests(SimpleTestCase):
    comp = SimpleNamespace(pk=1, comp_url='https://liftingcast.com/meets/abc/results')

    def test_success_returns_the_athletes_and_no_error(self):
        with mock.patch.object(scrape_athlete_data, '_scrape_athletes_once', return_value=[athlete_row('ana')]):
            comp, athletes, error = scrape_athletes_only(self.comp)

        self.assertIs(comp, self.comp)
        self.assertEqual(len(athletes), 1)
        self.assertIsNone(error)

    def test_failed_scrape_is_retried(self):
        attempts = [TimeoutError('slow'), [athlete_row('ana')]]
        with mock.patch.object(scrape_athlete_data, '_scrape_athletes_once', side_effect=attempts) as once:
            _, athletes, error = scrape_athletes_only(self.comp)

        self.assertEqual(once.call_count, 2)
        self.assertEqual(len(athletes), 1)
        self.assertIsNone(error)

    def test_error_is_returned_once_every_attempt_has_failed(self):
        with mock.patch.object(scrape_athlete_data, '_scrape_athletes_once',
                               side_effect=TimeoutError('slow')) as once:
            _, athletes, error = scrape_athletes_only(self.comp)

        self.assertEqual(once.call_count, scrape_athlete_data.SCRAPE_ATTEMPTS)
        self.assertEqual(athletes, [])
        self.assertEqual(error, 'TimeoutError: slow')


class ScrapeAndSaveAthletesTests(TestCase):
    def setUp(self):
        self.comp = make_competition('test meet', '2026-11-14')

    def test_scraped_athletes_are_saved_and_counted(self):
        scraped = (self.comp, [athlete_row('ana'), athlete_row('bea')], None)
        with mock.patch.object(scrape_athlete_data, 'scrape_athletes_only', return_value=scraped):
            self.assertEqual(scrape_and_save_athletes(self.comp), 2)

        self.assertEqual(self.comp.athletes.count(), 2)

    def test_failed_scrape_saves_nothing(self):
        save_athletes_to_db(self.comp, [athlete_row('ana')])
        with mock.patch.object(scrape_athlete_data, 'scrape_athletes_only',
                               return_value=(self.comp, [], 'TimeoutError: slow')):
            self.assertEqual(scrape_and_save_athletes(self.comp), 0)

        self.assertEqual(self.comp.athletes.count(), 1)


class ScrapeAthletesWithDriverTests(TempDirMixin, SimpleTestCase):
    comp = SimpleNamespace(pk=1, comp_url='https://liftingcast.com/meets/abc/results')

    def _scrape(self, content: str = SAMPLE_CSV):
        path = self.write('meet.csv', content)
        with mock.patch.object(scrape_athlete_data, '_open_fresh_tab') as fresh_tab, \
             mock.patch.object(scrape_athlete_data, '_export_athlete_csv', return_value=path):
            result = scrape_athletes_with_driver(mock.sentinel.driver, self.comp, self.tmp)
        fresh_tab.assert_called_once_with(mock.sentinel.driver, self.tmp)
        return result

    def test_returns_the_athletes_and_removes_the_download(self):
        _, athletes = self._scrape()

        self.assertEqual([a['name'] for a in athletes], ['ana oneil', 'bea stone'])
        self.assertEqual(os.listdir(self.tmp), [])

    def test_digest_only_changes_when_the_export_changes(self):
        first, _ = self._scrape()
        same, _ = self._scrape()
        changed, _ = self._scrape(SAMPLE_CSV.replace('"345"', '"350"'))

        self.assertEqual(first, same)
        self.assertNotEqual(first, changed)
