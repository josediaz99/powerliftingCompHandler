from datetime import date, datetime, timedelta
from unittest import mock

from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from ironCrawler.webscraping import scrape_competition_data
from ironCrawler.webscraping.scrape_competition_data import (
    _parse_competitions,
    _parse_mmddyyyy,
    get_competition_data,
)


def _meet_row(name: str, days_from_today: int, meet_id: str = 'abc') -> str:
    meet_date = (datetime.today() + timedelta(days=days_from_today)).strftime('%m/%d/%Y')
    return f'<tr><td><a href="/meets/{meet_id}/results">{name}</a></td><td>{meet_date}</td></tr>'


def _rows(*rows: str) -> list:
    return BeautifulSoup('<table>' + ''.join(rows) + '</table>', 'html.parser').find_all('tr')


class ParseDateTests(SimpleTestCase):
    def test_reads_month_day_year(self):
        self.assertEqual(_parse_mmddyyyy('02/26/2026'), date(2026, 2, 26))
        self.assertEqual(_parse_mmddyyyy('2/6/2026'), date(2026, 2, 6))

    def test_accepts_dash_and_dot_separators(self):
        self.assertEqual(_parse_mmddyyyy('02-26-2026'), date(2026, 2, 26))
        self.assertEqual(_parse_mmddyyyy('02.26.2026'), date(2026, 2, 26))

    def test_blank_or_unreadable_values_give_none(self):
        for value in (None, '', '   ', 'tbd', '2026/02/26'):
            self.assertIsNone(_parse_mmddyyyy(value))


class ParseCompetitionsTests(SimpleTestCase):
    def test_competition_is_read_from_a_table_row(self):
        competitions = _parse_competitions(_rows(_meet_row('Fall Classic', 2, meet_id='m123')))

        self.assertEqual(competitions, [{
            'name': 'Fall Classic',
            'link': 'https://liftingcast.com/meets/m123/results',
            'date': (datetime.today() + timedelta(days=2)).date().isoformat(),
        }])

    def test_only_today_through_the_next_seven_days_is_kept(self):
        competitions = _parse_competitions(_rows(
            _meet_row('yesterday', -1),
            _meet_row('today', 0),
            _meet_row('in a week', 7),
            _meet_row('in eight days', 8),
        ))

        self.assertEqual([c['name'] for c in competitions], ['today', 'in a week'])

    def test_row_that_cannot_be_parsed_is_skipped(self):
        competitions = _parse_competitions(_rows(
            '<tr><td>no link here</td></tr>',
            _meet_row('good row', 1),
        ))

        self.assertEqual([c['name'] for c in competitions], ['good row'])

    def test_row_without_a_readable_date_is_skipped(self):
        competitions = _parse_competitions(_rows(
            '<tr><td><a href="/meets/x/results">No Date</a></td><td>TBD</td></tr>',
            _meet_row('good row', 1),
        ))

        self.assertEqual([c['name'] for c in competitions], ['good row'])


class GetCompetitionDataTests(SimpleTestCase):
    def test_first_two_table_rows_are_not_competitions(self):
        html = ('<table><tr><th>header</th></tr><tr><th>filters</th></tr>'
                + _meet_row('Fall Classic', 1) + '</table>')
        with mock.patch.object(scrape_competition_data, 'create_webdriver') as create_webdriver, \
             mock.patch.object(scrape_competition_data, 'get_html', return_value=html) as get_html:
            competitions = get_competition_data()

        get_html.assert_called_once_with(create_webdriver.return_value)
        self.assertEqual([c['name'] for c in competitions], ['Fall Classic'])
