"""
ironCrawler/management/commands/scrape_competitions.py

Usage:
    python manage.py scrape_competitions
"""

from django.core.management.base import BaseCommand
from ironCrawler.scrape_competition_data import get_competition_data
from ironCrawler.models import Competition


class Command(BaseCommand):
    help = "Scrapes liftingcast.com for upcoming competitions and saves them to the database."

    def handle(self, *args, **options):
        self.stdout.write("Fetching competitions from liftingcast.com...")

        competitions = get_competition_data()

        if not competitions:
            self.stdout.write(self.style.WARNING("No competitions found within the next 7 days."))
            return

        created_count = 0
        for comp in competitions:
            obj, created = Competition.objects.get_or_create(
                comp_name=comp['name'],
                comp_date=comp['date'],
                defaults={'comp_url': comp['link']},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  + Saved: {obj}"))
            else:
                self.stdout.write(f"  ~ Already exists: {obj}")

        self.stdout.write(self.style.SUCCESS(f"\nDone. {created_count} new competition(s) saved."))