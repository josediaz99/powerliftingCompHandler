"""
ironCrawler/management/commands/run_scheduler.py

Starts the APScheduler background scheduler, which runs two jobs:
  - the full competition + athlete scrape every 3 hours, to stay current
    across time zones and pick up changes made before a competition
  - the live refresh every minute, for competitions that have begun

Usage:
    python manage.py run_scheduler
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.core.management.base import BaseCommand
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJob

from ironCrawler.webscraping.live_refresh import live_refresher
from ironCrawler.webscraping.scraper import scrape_and_load

logger = logging.getLogger("ironCrawler.scheduler")

FULL_SCRAPE_INTERVAL_HOURS = 3
# job ids from earlier versions; jobs are stored in the DB, so a renamed job would keep running
RETIRED_JOB_IDS = ["scrape_every_6h"]

def live_competition_job():
    """Every-minute job: refresh athletes for all competitions happening right now."""
    try:
        summary = live_refresher.refresh()
    except Exception:
        logger.exception("Live-competition job failed")
        return

    if not summary['live']:
        logger.debug("Live-competition job: no live competitions")
        return

    logger.info(
        "Live-competition job: %d live — updated: %d, unchanged: %d, failed: %d, not reached: %d (%.1fs)",
        summary['live'], summary['updated'], summary['unchanged'],
        summary['failed'], summary['not_reached'], summary['seconds'],
    )
    if summary['not_reached']:
        logger.warning(
            "Live-competition job ran out of time — %d competition(s) moved to the front of the next pass",
            summary['not_reached'],
        )


def scrape_job():
    """Scheduled job: scrape competitions and athletes, then load into the DB.

    Competitions that have begun are left to the live refresh, which already
    scrapes them every minute.
    """
    try:
        created, skipped, athletes, failed = scrape_and_load(skip_live=True)
        logger.info(
            "Scheduled scrape complete — created: %d, skipped: %d, athletes: %d, failed: %d",
            created, skipped, athletes, len(failed),
        )
        if failed:
            logger.error("Competitions that failed athlete scrape after retry: %s", ", ".join(failed))
    except Exception:
        logger.exception("Scheduled scrape failed")

class Command(BaseCommand):
    help = "Starts the background scheduler — full scrape every 3 hours, live refresh every minute."

    def handle(self, *args, **options):
        scheduler = BackgroundScheduler()
        scheduler.add_jobstore(DjangoJobStore(), "default")

        DjangoJob.objects.filter(id__in=RETIRED_JOB_IDS).delete()

        scheduler.add_job(
            scrape_job,
            trigger=IntervalTrigger(hours=FULL_SCRAPE_INTERVAL_HOURS),
            id="full_scrape",
            name="Scrape LiftingCast competitions",
            jobstore="default",
            replace_existing=True,
        )

        scheduler.add_job(
            live_competition_job,
            trigger=IntervalTrigger(minutes=1),
            id="live_competition_refresh",
            name="Refresh athletes for live competitions",
            jobstore="default",
            replace_existing=True,
            # never overlap passes; if one overruns, run once afterwards rather than catching up
            max_instances=1,
            coalesce=True,
        )

        logger.info("Starting scheduler...")
        scheduler.start()
        self.stdout.write(self.style.SUCCESS(
            f"Scheduler running — full scrape every {FULL_SCRAPE_INTERVAL_HOURS} h, "
            "live refresh every 1 min. Press Ctrl+C to stop."
        ))

        try:
            # Keep the process alive
            import time
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            live_refresher.close()
            self.stdout.write(self.style.WARNING("Scheduler stopped."))