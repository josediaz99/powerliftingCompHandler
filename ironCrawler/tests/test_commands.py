import os
import shutil
import tempfile
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django_apscheduler.models import DjangoJob

from ironCrawler.management.commands import run_scheduler, scrape_athletes, scrape_competitions
from ironCrawler.webscraping.create_selenium_driver import _ensure_directory_exists, _get_random_user

from .helpers import make_competition


class SchedulerJobTests(SimpleTestCase):
    def test_full_scrape_job_leaves_live_competitions_to_the_live_refresh(self):
        with mock.patch.object(run_scheduler, 'scrape_and_load', return_value=(1, 0, 5, [])) as scrape:
            run_scheduler.scrape_job()

        scrape.assert_called_once_with(skip_live=True)

    def test_full_scrape_job_survives_a_failed_scrape(self):
        with mock.patch.object(run_scheduler, 'scrape_and_load', side_effect=RuntimeError('boom')):
            run_scheduler.scrape_job()

    def test_live_job_survives_a_failed_pass(self):
        with mock.patch.object(run_scheduler.live_refresher, 'refresh', side_effect=RuntimeError('boom')):
            run_scheduler.live_competition_job()

    def test_live_job_runs_one_pass(self):
        summary = {'live': 2, 'updated': 1, 'unchanged': 1, 'failed': 0, 'not_reached': 0, 'seconds': 4.2}
        with mock.patch.object(run_scheduler.live_refresher, 'refresh', return_value=summary) as refresh:
            run_scheduler.live_competition_job()

        refresh.assert_called_once_with()


class RunSchedulerCommandTests(TestCase):
    def _run(self):
        """Runs the command with a fake scheduler, stopping it as soon as it starts waiting."""
        with mock.patch.object(run_scheduler, 'BackgroundScheduler') as scheduler_class, \
             mock.patch.object(run_scheduler.live_refresher, 'close') as close, \
             mock.patch('time.sleep', side_effect=KeyboardInterrupt):
            call_command('run_scheduler', stdout=StringIO())
        return scheduler_class.return_value, close

    def test_both_jobs_are_scheduled(self):
        scheduler, _ = self._run()

        jobs = {call.kwargs['id']: call for call in scheduler.add_job.call_args_list}
        self.assertEqual(set(jobs), {'full_scrape', 'live_competition_refresh'})
        self.assertEqual(jobs['full_scrape'].args[0], run_scheduler.scrape_job)
        self.assertEqual(jobs['full_scrape'].kwargs['trigger'].interval, timedelta(hours=3))
        self.assertEqual(jobs['live_competition_refresh'].args[0], run_scheduler.live_competition_job)
        self.assertEqual(jobs['live_competition_refresh'].kwargs['trigger'].interval, timedelta(minutes=1))

    def test_live_passes_never_overlap(self):
        scheduler, _ = self._run()

        jobs = {call.kwargs['id']: call for call in scheduler.add_job.call_args_list}
        self.assertEqual(jobs['live_competition_refresh'].kwargs['max_instances'], 1)

    def test_job_stored_under_a_retired_id_is_removed(self):
        DjangoJob.objects.create(id='scrape_every_6h', job_state=b'')
        self._run()

        self.assertFalse(DjangoJob.objects.filter(id='scrape_every_6h').exists())

    def test_stopping_the_scheduler_closes_the_live_drivers(self):
        scheduler, close = self._run()

        scheduler.shutdown.assert_called_once_with()
        close.assert_called_once_with()


class ScrapeCommandTests(TestCase):
    def test_scrape_competitions_reports_the_sync(self):
        out = StringIO()
        with mock.patch.object(scrape_competitions, 'scrape_and_load',
                               return_value=(2, 1, 40, ['broken meet'])) as scrape:
            call_command('scrape_competitions', stdout=out)

        scrape.assert_called_once_with()
        self.assertIn('Competitions created: 2', out.getvalue())
        self.assertIn('broken meet', out.getvalue())

    def test_scrape_athletes_scrapes_every_selected_competition(self):
        make_competition('a', '2026-11-14')
        make_competition('b', '2026-11-15')
        make_competition('off', '2026-11-15', scrape_enabled=False)
        out = StringIO()
        with mock.patch.object(scrape_athletes, 'scrape_and_save_athletes', return_value=7) as scrape:
            call_command('scrape_athletes', stdout=out)

        self.assertEqual(scrape.call_count, 2)
        self.assertIn('Total athletes scraped: 14', out.getvalue())

    def test_scrape_athletes_with_nothing_selected_does_nothing(self):
        make_competition('off', '2026-11-15', scrape_enabled=False)
        out = StringIO()
        with mock.patch.object(scrape_athletes, 'scrape_and_save_athletes') as scrape:
            call_command('scrape_athletes', stdout=out)

        scrape.assert_not_called()
        self.assertIn('No competitions are selected', out.getvalue())


class SeleniumDriverHelperTests(SimpleTestCase):
    def test_download_directory_is_created_and_returned_as_an_absolute_path(self):
        parent = tempfile.mkdtemp(prefix="lc_test_")
        self.addCleanup(shutil.rmtree, parent, ignore_errors=True)

        created = _ensure_directory_exists(os.path.join(parent, 'downloads'))

        self.assertTrue(os.path.isdir(created))
        self.assertTrue(os.path.isabs(created))

    def test_user_agent_is_a_windows_chrome_agent(self):
        user_agent = _get_random_user()

        self.assertTrue(user_agent.startswith('Mozilla/5.0 (Windows NT 10.0; Win64; x64)'))
        self.assertIn('Chrome/', user_agent)
