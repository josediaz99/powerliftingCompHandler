"""Shared builders for the ironCrawler tests."""

from ironCrawler.models import Competition


def athlete_row(name: str, total: str = '0', **fields) -> dict:
    """Builds a cleaned CSV row dict the way _athlete_data_to_dicts returns it."""
    return {'name': name, 'gender': 'female', 'weight class': '63', 'total': total, **fields}


def make_competition(name: str, comp_date, scrape_enabled: bool = True) -> Competition:
    """Stores a competition, selected for scraping unless told otherwise."""
    return Competition.objects.create(
        comp_name=name, comp_url=f'https://liftingcast.com/meets/{name}/results', comp_date=comp_date,
        scrape_enabled=scrape_enabled)
