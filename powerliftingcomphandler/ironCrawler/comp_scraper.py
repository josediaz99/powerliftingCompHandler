"""
comp_scraper.py — IronCrawler · LiftingCast Competition Scraper
===========================================================
Scrapes upcoming and recent competitions from liftingcast.com
using Selenium (headless Chrome) + BeautifulSoup, then loads
them into the Django Competition model.

Requirements:
    pip install selenium beautifulsoup4

Design decisions:
    - Dynamic rendering: LiftingCast is a react built web app, so a 
      static HTTP request won't work. Selenium with headless Chrome 
      is used to wait for the table to fully populate before parsing.
    - Anti-detection: random User-Agent rotation + webdriver flag
      removal reduce the likelihood of bot detection.
    - Date range: only competitions within DATE_RANGE_DAYS of today
      are collected, keeping the dataset relevant and the DB lean.
    - Upsert strategy: get_or_create avoids duplicate rows while
      still allowing URL updates on re-scrapes.
"""

import os
import re
import random
import logging
from datetime import datetime, timedelta, date

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .models import Competition

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

BASE_URL = "https://liftingcast.com"

# CSS selectors used to detect when the page has fully loaded
_CSS_ROW   = "div.meets-table-table-wrapper table.table tbody tr"
_CSS_LINKS = "div.meets-table-table-wrapper table.table a[href]"

# How many days ahead to collect competitions (default: next 7 days)
DATE_RANGE_DAYS = 7

# Selenium wait timeout in seconds
WAIT_TIMEOUT = 60

# Rotate through recent Chrome User-Agents to reduce bot detection
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _random_user_agent() -> str:
    """Return a random User-Agent string from the pool."""
    return random.choice(_USER_AGENTS)


def _parse_date(raw: str) -> date | None:
    """
    Parse a date string in MM/DD/YYYY format (with optional dash/dot
    separators) into a datetime.date object.

    Returns None if the value is empty or cannot be parsed.
    """
    if not raw:
        return None

    # Normalise separators: 02-28-2026 -> 02/28/2026
    normalised = re.sub(r"[-.]", "/", str(raw).strip())

    try:
        return datetime.strptime(normalised, "%m/%d/%Y").date()
    except ValueError:
        logger.warning("Could not parse date: %r", raw)
        return None


def _cutoff_date(days: int = DATE_RANGE_DAYS) -> date:
    """Return today's date plus *days* days."""
    return (datetime.today() + timedelta(days=days)).date()


def _build_driver(download_dir: str) -> webdriver.Chrome:
    """
    Configure and return a headless Chrome WebDriver.

    Options applied:
        - Headless mode with a realistic viewport
        - Disabled GPU (required for headless stability)
        - AutomationControlled flag stripped (anti-bot measure)
        - Random User-Agent header
        - Silent download directory pre-configured
    """
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-agent={_random_user_agent()}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option("prefs", {
        "download.default_directory":   download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade":   True,
        "safebrowsing.enabled":         True,
    })

    driver = webdriver.Chrome(options=options)

    # Remove the navigator.webdriver flag that many sites check
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    # Enable headless file downloads via CDP
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior":     "allow",
        "downloadPath": download_dir,
    })

    return driver


def _fetch_competition_rows(driver: webdriver.Chrome) -> list:
    """
    Navigate to LiftingCast, wait for the competition table to populate,
    and return a list of BeautifulSoup <tr> elements for competition rows.

    The first two rows are header/title rows and are discarded.
    """
    wait = WebDriverWait(driver, WAIT_TIMEOUT)

    driver.get(BASE_URL)

    # Wait until at least one data row exists
    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, _CSS_ROW)))

    # Wait until the table has enough anchor links to be considered loaded
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, _CSS_LINKS)) >= 5)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    all_rows = soup.find_all("tr")

    # Skip the two header rows (title row + column header row)
    return all_rows[2:]


def _parse_competition_rows(rows: list, cutoff: date) -> list[dict]:
    """
    Extract competition data from <tr> elements up to *cutoff* date.

    Each returned dict contains:
        comp_name (str)  -- competition title
        comp_url  (str)  -- full URL to the results page
        comp_date (str)  -- ISO date string "YYYY-MM-DD"

    Rows that cannot be parsed (e.g. section headers) are skipped with
    a warning. Iteration stops once a competition date exceeds *cutoff*.
    """
    competitions = []

    for row in rows:
        try:
            cells = row.find_all("td")

            # Rows without at least 2 <td> elements are headers or footers
            if len(cells) < 2 or not cells[0].a:
                continue

            name     = cells[0].a.get_text(strip=True)
            rel_url  = cells[0].a.get("href", "")
            raw_date = cells[1].get_text(strip=True)

            comp_date = _parse_date(raw_date)
            if comp_date is None:
                continue

            # Stop once we have passed the desired date range
            if comp_date > cutoff:
                break

            competitions.append({
                "comp_name": name,
                "comp_url":  BASE_URL + rel_url,
                "comp_date": comp_date.isoformat(),  # "YYYY-MM-DD"
            })

        except Exception:
            logger.warning("Skipped unparseable row: %s", row, exc_info=True)

    return competitions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_competitions(date_range_days: int = DATE_RANGE_DAYS) -> list[dict]:
    """
    Launch a headless browser, scrape LiftingCast, and return a list of
    competition dicts for events within *date_range_days* of today.

    Each dict contains: comp_name, comp_url, comp_date (ISO string).
    """
    download_dir = os.path.abspath("data")
    os.makedirs(download_dir, exist_ok=True)

    cutoff = _cutoff_date(date_range_days)
    driver = _build_driver(download_dir)

    try:
        rows         = _fetch_competition_rows(driver)
        competitions = _parse_competition_rows(rows, cutoff)
    finally:
        # Always quit the driver to free browser resources
        driver.quit()

    logger.info("Scraped %d competitions (cutoff: %s)", len(competitions), cutoff)
    return competitions


def load_competitions(competitions: list[dict]) -> tuple[int, int]:
    """
    Upsert a list of competition dicts into the Django Competition model.

    Returns:
        (created_count, skipped_count)
    """
    created = skipped = 0

    for comp in competitions:
        _, was_created = Competition.objects.get_or_create(
            comp_name=comp["comp_name"],
            comp_date=comp["comp_date"],
            defaults={"comp_url": comp["comp_url"]},
        )
        if was_created:
            created += 1
        else:
            skipped += 1

    logger.info("DB load complete -- created: %d, skipped: %d", created, skipped)
    return created, skipped


def scrape_and_load_comps(date_range_days: int = DATE_RANGE_DAYS) -> tuple[int, int]:
    """
    Convenience entry point: scrape LiftingCast then load results into the DB.

    Returns:
        (created_count, skipped_count)
    """
    competitions = scrape_competitions(date_range_days)
    return load_competitions(competitions)