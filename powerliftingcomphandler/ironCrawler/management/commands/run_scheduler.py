"""
run_scheduler.py
Starts the APScheduler background scheduler which fires the
competition scraper once daily at midnight.

Usage:
    python manage.py run_scheduler
"""

import logging
from django.core.management.base import BaseCommand
from django_apscheduler.jobstores import DjangoJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ironCrawler.scraper import scrape_and_load

logger = logging.getLogger(__name__)


def scrape_job():
    """Scheduled job: scrape competitions and load into the DB."""
    try:
        created, skipped = scrape_and_load()
        logger.info("Scheduled scrape complete — created: %d, skipped: %d", created, skipped)
    except Exception:
        logger.exception("Scheduled scrape failed")


class Command(BaseCommand):
    help = "Starts the background scheduler for daily competition scraping."

    def handle(self, *args, **options):
        scheduler = BackgroundScheduler()
        scheduler.add_jobstore(DjangoJobStore(), "default")

        scheduler.add_job(
            scrape_job,
            trigger=CronTrigger(hour=6, minute=0),  # 6 AM daily
            id="daily_scrape",
            name="Scrape LiftingCast competitions",
            jobstore="default",
            replace_existing=True,
        )

        logger.info("Starting scheduler...")
        scheduler.start()
        self.stdout.write(self.style.SUCCESS("Scheduler running — press Ctrl+C to stop."))

        try:
            # Keep the process alive
            import time
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            self.stdout.write(self.style.WARNING("Scheduler stopped."))