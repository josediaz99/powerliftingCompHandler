from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ironCrawler.models import Athlete, Competition
from ironCrawler.webscraping.scrape_athlete_data import save_athletes_to_db

from .helpers import athlete_row, make_competition


class ViewTests(TestCase):
    def setUp(self):
        self.comp = make_competition('fall classic', '2026-11-14')
        self.other = make_competition('spring open', '2026-11-12')
        save_athletes_to_db(self.comp, [
            athlete_row('ana', total='345', **{'best squat': '127.5', 'dots points': '371.3'}),
            athlete_row('bea'),
        ])
        save_athletes_to_db(self.other, [athlete_row('cat')])
        self.ana = Athlete.objects.get(athlete_name='ana')


class IndexTests(ViewTests):
    def test_competitions_are_listed_in_date_order(self):
        response = self.client.get(reverse('index'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([c.comp_name for c in response.context['competitions']],
                         ['spring open', 'fall classic'])
        self.assertContains(response, reverse('athlete_select', args=[self.comp.comp_id]))

    def test_competitions_not_selected_for_scraping_are_not_listed(self):
        make_competition('hidden meet', '2026-11-13', scrape_enabled=False)

        self.assertNotContains(self.client.get(reverse('index')), 'hidden meet')

    def test_visitors_get_a_login_link_and_admins_a_manage_link(self):
        self.assertContains(self.client.get(reverse('index')), reverse('login'))

        self.client.force_login(get_user_model().objects.create_user('coach', password='pw', is_staff=True))
        self.assertContains(self.client.get(reverse('index')), reverse('manage_competitions'))

    def test_page_renders_with_no_competitions(self):
        self.comp.delete()
        self.other.delete()

        self.assertContains(self.client.get(reverse('index')), 'No competitions loaded')


class AthleteSelectTests(ViewTests):
    def test_roster_of_the_competition_is_shown(self):
        response = self.client.get(reverse('athlete_select', args=[self.comp.comp_id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual([a.athlete_name for a in response.context['athletes']], ['ana', 'bea'])
        self.assertContains(response, reverse('athlete_dash', args=[self.ana.id]))

    def test_unknown_competition_is_a_404(self):
        self.assertEqual(self.client.get(reverse('athlete_select', args=[9999])).status_code, 404)


class AthleteDashTests(ViewTests):
    def test_dashboard_gets_the_athlete_and_their_competitors(self):
        response = self.client.get(reverse('athlete_dash', args=[self.ana.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['athlete'], self.ana)
        self.assertEqual(sorted(a['name'] for a in response.context['pool']), ['ana', 'bea'])

    def test_dashboard_polls_its_own_data_url_instead_of_a_manual_refresh(self):
        response = self.client.get(reverse('athlete_dash', args=[self.ana.id]))

        self.assertContains(response, reverse('athlete_dash_data', args=[self.ana.id]))
        self.assertNotContains(response, 'refreshBtn')

    def test_compare_filter_is_made_of_checkboxes(self):
        response = self.client.get(reverse('athlete_dash', args=[self.ana.id]))

        self.assertContains(response, 'type="checkbox"', count=2)

    def test_dashboard_names_the_competition(self):
        response = self.client.get(reverse('athlete_dash', args=[self.ana.id]))

        self.assertContains(response, '<div class="ath-comp">fall classic</div>')

    def test_unknown_athlete_is_a_404(self):
        self.assertEqual(self.client.get(reverse('athlete_dash', args=[9999])).status_code, 404)


class AthleteDashDataTests(ViewTests):
    def test_pool_holds_every_athlete_in_the_same_competition(self):
        response = self.client.get(reverse('athlete_dash_data', args=[self.ana.id]))

        self.assertEqual(response.status_code, 200)
        pool = {a['name']: a for a in response.json()['pool']}
        self.assertEqual(sorted(pool), ['ana', 'bea'])
        self.assertEqual(pool['ana'], {
            'id': self.ana.id, 'name': 'ana', 'gender': 'female', 'weight': '63',
            'division': '', 'category': '', 'total': 345.0, 'dots': 371.3,
            'squat': 127.5, 'bench': 0.0, 'deadlift': 0.0,
        })

    def test_missing_dots_score_is_sent_as_zero(self):
        response = self.client.get(reverse('athlete_dash_data', args=[self.ana.id]))

        pool = {a['name']: a for a in response.json()['pool']}
        self.assertEqual(pool['bea']['dots'], 0)

    def test_data_reflects_a_later_scrape(self):
        save_athletes_to_db(self.comp, [athlete_row('ana', total='350'), athlete_row('bea')])
        response = self.client.get(reverse('athlete_dash_data', args=[self.ana.id]))

        pool = {a['name']: a for a in response.json()['pool']}
        self.assertEqual(pool['ana']['total'], 350.0)

    def test_withdrawn_athlete_is_a_404(self):
        save_athletes_to_db(self.comp, [athlete_row('bea')])

        self.assertEqual(self.client.get(reverse('athlete_dash_data', args=[self.ana.id])).status_code, 404)


class AdminTests(ViewTests):
    def setUp(self):
        super().setUp()
        users = get_user_model().objects
        self.admin = users.create_user('coach', password='iron-pw-1', is_staff=True)
        self.lifter = users.create_user('lifter', password='iron-pw-2')
        self.off = make_competition('winter cup', '2026-11-16', scrape_enabled=False)
        self.manage_url = reverse('manage_competitions')
        self.login_redirect = f"{reverse('login')}?next={self.manage_url}"

    def _toggle(self, competition, enabled, **extra):
        return self.client.post(reverse('toggle_competition_scrape', args=[competition.comp_id]),
                                {'enabled': enabled}, **extra)


class LoginTests(AdminTests):
    def test_admin_logs_in_and_lands_on_the_manage_page(self):
        response = self.client.post(reverse('login'), {'username': 'coach', 'password': 'iron-pw-1'})

        self.assertRedirects(response, self.manage_url)

    def test_wrong_password_is_rejected(self):
        response = self.client.post(reverse('login'), {'username': 'coach', 'password': 'nope'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'form-error')
        self.assertRedirects(self.client.get(self.manage_url), self.login_redirect)

    def test_account_that_is_not_staff_cannot_log_in(self):
        response = self.client.post(reverse('login'), {'username': 'lifter', 'password': 'iron-pw-2'})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_ends_the_session(self):
        self.client.force_login(self.admin)

        self.assertRedirects(self.client.post(reverse('logout')), reverse('index'))
        self.assertEqual(self.client.get(self.manage_url).status_code, 302)


class ManageCompetitionsTests(AdminTests):
    def test_anonymous_visitor_is_sent_to_the_login_page(self):
        self.assertRedirects(self.client.get(self.manage_url), self.login_redirect)

    def test_logged_in_account_that_is_not_staff_is_refused(self):
        self.client.force_login(self.lifter)

        self.assertEqual(self.client.get(self.manage_url).status_code, 302)
        self.assertEqual(self._toggle(self.off, '1').status_code, 302)
        self.off.refresh_from_db()
        self.assertFalse(self.off.scrape_enabled)

    def test_competitions_are_split_into_the_scrape_list_and_the_rest(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.manage_url)

        self.assertEqual([c.comp_name for c in response.context['scheduled']],
                         ['spring open', 'fall classic'])
        self.assertEqual([c.comp_name for c in response.context['available']], ['winter cup'])
        self.assertContains(response, 'from the scrape list">&minus;</button>', count=2)
        self.assertContains(response, 'to the scrape list">+</button>', count=1)
        self.assertContains(response, '2 athletes stored')

    def test_both_lists_are_sorted_by_date(self):
        make_competition('early add', '2026-11-11', scrape_enabled=False)
        make_competition('late pick', '2026-11-20')
        self.client.force_login(self.admin)
        response = self.client.get(self.manage_url)

        self.assertEqual([c.comp_name for c in response.context['scheduled']],
                         ['spring open', 'fall classic', 'late pick'])
        self.assertEqual([c.comp_name for c in response.context['available']],
                         ['early add', 'winter cup'])

    def test_scrape_list_comes_before_the_other_meets_in_the_page(self):
        self.client.force_login(self.admin)
        page = self.client.get(self.manage_url).content.decode()

        self.assertLess(page.index('id="scheduledList"'), page.index('id="availableList"'))

    def test_empty_lists_say_so(self):
        Competition.objects.update(scrape_enabled=False)
        self.client.force_login(self.admin)
        response = self.client.get(self.manage_url)

        self.assertContains(response, '<div class="empty show" id="scheduledEmpty"')
        self.assertContains(response, '<div class="empty" id="availableEmpty"')


class ToggleCompetitionScrapeTests(AdminTests):
    def test_anonymous_visitor_cannot_toggle(self):
        self.assertEqual(self._toggle(self.off, '1').status_code, 302)
        self.off.refresh_from_db()
        self.assertFalse(self.off.scrape_enabled)

    def test_admin_switches_a_competition_on_and_off(self):
        self.client.force_login(self.admin)

        self.assertRedirects(self._toggle(self.off, '1'), self.manage_url)
        self.off.refresh_from_db()
        self.assertTrue(self.off.scrape_enabled)

        self._toggle(self.off, '0')
        self.off.refresh_from_db()
        self.assertFalse(self.off.scrape_enabled)

    def test_adding_moves_the_competition_to_the_scrape_list_and_says_so(self):
        self.client.force_login(self.admin)
        response = self._toggle(self.off, '1', follow=True)

        self.assertIn('winter cup', [c.comp_name for c in response.context['scheduled']])
        self.assertEqual(response.context['available'], [])
        self.assertContains(response, 'Added winter cup to the scrape list')

    def test_removing_moves_the_competition_back_and_says_so(self):
        self.client.force_login(self.admin)
        response = self._toggle(self.comp, '0', follow=True)

        self.assertEqual([c.comp_name for c in response.context['available']],
                         ['fall classic', 'winter cup'])
        self.assertContains(response, 'Removed fall classic from the scrape list')

    def test_switching_off_keeps_the_athletes_already_stored(self):
        self.client.force_login(self.admin)
        self._toggle(self.comp, '0')

        self.assertEqual(self.comp.athletes.count(), 2)

    def test_script_request_gets_the_saved_state_as_json(self):
        self.client.force_login(self.admin)
        response = self._toggle(self.off, '1', headers={'X-Requested-With': 'fetch'})

        self.assertEqual(response.json(), {
            'comp_id': self.off.comp_id, 'scrape_enabled': True,
            'message': 'Added winter cup to the scrape list',
        })

    def test_toggle_must_be_a_post(self):
        self.client.force_login(self.admin)

        self.assertEqual(self.client.get(
            reverse('toggle_competition_scrape', args=[self.off.comp_id])).status_code, 405)

    def test_unknown_competition_is_a_404(self):
        self.client.force_login(self.admin)

        self.assertEqual(self.client.post(
            reverse('toggle_competition_scrape', args=[9999]), {'enabled': '1'}).status_code, 404)

    def test_new_competitions_start_switched_off(self):
        created = Competition.objects.create(
            comp_name='new', comp_url='https://liftingcast.com', comp_date='2026-11-17')

        self.assertFalse(created.scrape_enabled)
