"""
ironCrawler/scraper.py

Provides scrape_and_load() — the single entry point used by the scheduler
and management commands to sync liftingcast.com competitions with the DB.

Behaviour:
  - Creates competitions that don't exist yet
  - Removes competitions that have disappeared from the site
  - Returns (created_count, skipped_count) so callers can log the result
"""

import logging
from ironCrawler.scrape_competition_data import get_competition_data
from ironCrawler.models import Competition

logger = logging.getLogger(__name__)


def scrape_and_load() -> tuple[int, int]:
    """
    Scrapes liftingcast.com for upcoming competitions and syncs them with
    the Competition table.

    - New competitions are created.
    - Competitions no longer returned by the scraper are deleted.

    Returns:
        (created_count, skipped_count)
    """
    logger.info("Starting competition scrape...")
    live_competitions = get_competition_data()

    if not live_competitions:
        logger.warning("Scraper returned no competitions — skipping DB sync to avoid wiping data.")
        return 0, 0

    created  = 0
    skipped  = 0
    live_keys = set()   # (name, date) pairs seen in this scrape run

    for comp in live_competitions:
        name = comp['name']
        date = comp['date']
        link = comp['link']

        obj, was_created = Competition.objects.get_or_create(
            comp_name=name,
            comp_date=date,
            defaults={'comp_url': link},
        )

        live_keys.add((name, date))

        if was_created:
            created += 1
            logger.info("Created: %s (%s)", name, date)
        else:
            skipped += 1
            logger.debug("Already exists: %s (%s)", name, date)

    # ── Remove stale competitions (no longer on liftingcast) ──────────────

    # More precise: only delete if BOTH name AND date are absent
    stale_qs = Competition.objects.all()
    for comp_obj in stale_qs:
        if (comp_obj.comp_name, str(comp_obj.comp_date)) not in live_keys:
            logger.info("Removing stale competition: %s (%s)", comp_obj.comp_name, comp_obj.comp_date)
            comp_obj.delete()

    logger.info("Sync complete — created: %d, skipped: %d", created, skipped)
    return created, skipped