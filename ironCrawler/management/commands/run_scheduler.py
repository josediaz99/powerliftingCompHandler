"""
run_scheduler.py
Starts the APScheduler background scheduler which fires the
competition scraper every 6 hours to stay current across time zones.

Usage:
    python manage.py run_scheduler
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_apscheduler.jobstores import DjangoJobStore

from ironCrawler.models import Competition
from ironCrawler.webscraping.scrape_athlete_data import (
    save_athletes_to_db,
    scrape_athletes_only,
)
from ironCrawler.webscraping.scraper import scrape_and_load

logger = logging.getLogger("ironCrawler.scheduler")

def live_competition_job():
    """Every-minute job: refresh athletes for all competitions happening today."""
    today = timezone.localdate()
    live = list(Competition.objects.filter(comp_date=today))

    if not live:
        logger.debug("Live-competition job: no competitions today (%s)", today)
        return

    logger.info("Live-competition job: refreshing athletes for %d competition(s) on %s", len(live), today)

    for comp in live:
        _, athletes_data, error = scrape_athletes_only(comp)
        if error:
            logger.warning("Live refresh failed for %s: %s", comp, error)
        else:
            save_athletes_to_db(comp, athletes_data)
            logger.info("Live refresh complete for %s — %d athletes updated", comp, len(athletes_data))


def scrape_job():
    """Scheduled job: scrape competitions and athletes, then load into the DB."""
    try:
        created, skipped, athletes, failed = scrape_and_load()
        logger.info(
            "Scheduled scrape complete — created: %d, skipped: %d, athletes: %d, failed: %d",
            created, skipped, athletes, len(failed),
        )
        if failed:
            logger.warning("Competitions that failed athlete scrape: %s", ", ".join(failed))
    except Exception:
        logger.exception("Scheduled scrape failed")

class Command(BaseCommand):
    help = "Starts the background scheduler — scrapes competitions every 6 hours."

    def handle(self, *args, **options):
        scheduler = BackgroundScheduler()
        scheduler.add_jobstore(DjangoJobStore(), "default")

        scheduler.add_job(
            scrape_job,
            trigger=IntervalTrigger(hours=6),
            id="scrape_every_6h",
            name="Scrape LiftingCast competitions",
            jobstore="default",
            replace_existing=True,
        )

        scheduler.add_job(
            live_competition_job,
            trigger=IntervalTrigger(minutes=1),
            id="live_competition_refresh",
            name="Refresh athletes for today's competitions",
            jobstore="default",
            replace_existing=True,
        )

        logger.info("Starting scheduler...")
        scheduler.start()
        self.stdout.write(self.style.SUCCESS(
            "Scheduler running — full scrape every 6 h, live refresh every 1 min. Press Ctrl+C to stop."
        ))

        try:
            # Keep the process alive
            import time
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            self.stdout.write(self.style.WARNING("Scheduler stopped."))