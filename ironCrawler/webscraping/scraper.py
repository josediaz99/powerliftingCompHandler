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
from concurrent.futures import ThreadPoolExecutor, as_completed
from ironCrawler.webscraping.scrape_competition_data import get_competition_data
from ironCrawler.webscraping.scrape_athlete_data import scrape_and_save_athletes
from ironCrawler.models import Competition

# Each worker is a full Chrome instance — keep this low to avoid OOM.
MAX_SCRAPE_WORKERS = 4

logger = logging.getLogger(__name__)


def scrape_and_load() -> tuple[int, int, int]:
    """
    Scrapes liftingcast.com for upcoming competitions and syncs them with
    the Competition table. Then scrapes athletes for all competitions.

    - New competitions are created.
    - Competitions no longer returned by the scraper are deleted.
    - Athletes are scraped and saved for all competitions.

    Returns:
        (created_count, skipped_count, athletes_count)
    """
    logger.info("Starting competition scrape...")
    live_competitions = get_competition_data()

    if not live_competitions:
        logger.warning("Scraper returned no competitions — skipping DB sync to avoid wiping data.")
        return 0, 0, 0

    created  = 0
    skipped  = 0
    live_keys = set()   # (name, date) pairs seen in this scrape run

    for comp in live_competitions:
        name = comp['name']
        date = comp['date']
        link = comp['link']

        _, was_created = Competition.objects.get_or_create(
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

    logger.info("Competition sync complete — created: %d, skipped: %d", created, skipped)

    # ── Scrape athletes for all competitions (parallel) ───────────────────
    logger.info("Starting athlete scrape...")
    athletes_total = 0
    competitions = list(Competition.objects.all())
    n_workers = min(MAX_SCRAPE_WORKERS, len(competitions)) if competitions else 1

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(scrape_and_save_athletes, comp): comp for comp in competitions}
        for future in as_completed(futures):
            comp = futures[future]
            count = future.result()  # exceptions are caught inside scrape_and_save_athletes
            athletes_total += count
            logger.info("Saved %d athletes for %s", count, comp)

    logger.info("Full sync complete — competitions created: %d, skipped: %d, athletes: %d", created, skipped, athletes_total)
    return created, skipped, athletes_total