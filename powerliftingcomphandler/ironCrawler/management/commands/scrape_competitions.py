"""
ironCrawler/management/commands/scrape_competitions.py

loops over every competition on lifting cast which is sceduled within
the next week and stores them to database and removing those which
have past

Usage:
    python manage.py scrape_competitions
"""

from django.core.management.base import BaseCommand
from ironCrawler.scraper import scrape_and_load


class Command(BaseCommand):
    help = "Scrapes liftingcast.com for upcoming competitions and saves them to the database."

    def handle(self, *args, **options):
        self.stdout.write("Fetching competitions from liftingcast.com and syncing with database...")

        created, skipped, athletes = scrape_and_load()

        self.stdout.write(self.style.SUCCESS(f"\nSync complete:"))
        self.stdout.write(f"  - Competitions created: {created}")
        self.stdout.write(f"  - Competitions skipped: {skipped}")
        self.stdout.write(f"  - Athletes scraped: {athletes}")