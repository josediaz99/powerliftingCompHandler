"""
ironCrawler/management/commands/scrape_athletes.py

loops over competitions stored in the dataase and downloads, cleans, and stores
athlete data from each comps url 


Usage:
    python manage.py scrape_athletes_data
"""

from django.core.management.base import BaseCommand, CommandError
 
from ironCrawler.models import Competition
from ironCrawler.scrape_athlete_data import scrape_and_save_athletes


class Command(BaseCommand):
    help = "Scrapes athlete data for all competitions in the database."

    def handle(self, *args, **options):
        competitions = Competition.objects.all()
        if not competitions:
            self.stdout.write(self.style.WARNING("No competitions found in database."))
            return

        total_athletes = 0
        for competition in competitions:
            self.stdout.write(f"Scraping athletes for: {competition}")
            athlete_count = scrape_and_save_athletes(competition)
            total_athletes += athlete_count
            self.stdout.write(self.style.SUCCESS(f"  Saved {athlete_count} athletes"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. Total athletes scraped: {total_athletes}"))
