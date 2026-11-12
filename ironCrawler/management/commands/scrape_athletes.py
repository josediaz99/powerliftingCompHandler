"""
ironCrawler/management/commands/scrape_athletes.py

loops over the competitions an admin has selected for scraping and downloads,
cleans, and stores athlete data from each comps url


Usage:
    python manage.py scrape_athletes
"""

from django.core.management.base import BaseCommand

from ironCrawler.models import Competition
from ironCrawler.webscraping.scrape_athlete_data import scrape_and_save_athletes


class Command(BaseCommand):
    help = "Scrapes athlete data for the competitions selected for scraping."

    def handle(self, *args, **options):
        competitions = Competition.objects.filter(scrape_enabled=True)
        if not competitions:
            self.stdout.write(self.style.WARNING("No competitions are selected for scraping."))
            return

        total_athletes = 0
        for competition in competitions:
            self.stdout.write(f"Scraping athletes for: {competition}")
            athlete_count = scrape_and_save_athletes(competition)
            total_athletes += athlete_count
            self.stdout.write(self.style.SUCCESS(f"  Saved {athlete_count} athletes"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. Total athletes scraped: {total_athletes}"))
