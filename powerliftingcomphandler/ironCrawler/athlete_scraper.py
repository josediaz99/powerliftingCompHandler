"""
athlete_scraper.py
------------------
Downloads the CSV export from a liftingcast competition results page.

Usage:
    from athlete_scraper import download_competition_csv
    csv_path = download_competition_csv(comp_url, download_dir)
"""

import os
import glob
import time
import random
import logging
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
WAIT_TIMEOUT = 60
CSV_TIMEOUT  = 120

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


# ── Private helpers ─────────────────────────────────────────────────────────

def _random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def _build_driver(download_dir: str) -> webdriver.Chrome:
    """Creates a headless Chrome driver with download preferences."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(f"--user-agent={_random_user_agent()}")
    options.add_experimental_option("prefs", {
        "download.default_directory":  download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade":  True,
        "safebrowsing.enabled":        True,
    })

    driver = webdriver.Chrome(options=options)

    # Remove webdriver flag to reduce bot detection
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    # Allow headless downloads
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior":     "allow",
        "downloadPath": download_dir,
    })

    return driver


def _wait_for_new_csv(download_dir: str, before_files: set, timeout: int = CSV_TIMEOUT) -> str:
    """
    Polls the download directory until a new CSV appears.
    Returns the path of the newly downloaded file.
    Raises TimeoutError if no file appears within `timeout` seconds.
    """
    end = time.time() + timeout
    while time.time() < end:
        # Still downloading?
        if glob.glob(os.path.join(download_dir, "*.crdownload")):
            time.sleep(0.5)
            continue

        current   = set(glob.glob(os.path.join(download_dir, "*.csv")))
        new_files = current - before_files
        if new_files:
            return max(new_files, key=os.path.getmtime)

        time.sleep(0.5)

    raise TimeoutError("CSV download did not complete within the timeout period.")


# ── Public API ──────────────────────────────────────────────────────────────

def download_competition_csv(comp_url: str, download_dir: str | None = None) -> str:
    """
    Navigates to a liftingcast competition results page, clicks Export,
    confirms the modal, and waits for the CSV to download.

    Parameters
    ----------
    comp_url     : Full URL to the competition results page
                   e.g. "https://liftingcast.com/meets/m8qa2atep5qi/results"
    download_dir : Directory to save the CSV. Defaults to a 'data' folder
                   next to this file.

    Returns
    -------
    str : Absolute path to the downloaded CSV file.
    """
    if download_dir is None:
        download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    Path(download_dir).mkdir(parents=True, exist_ok=True)
    download_dir = os.path.abspath(download_dir)

    # Snapshot existing CSVs before starting so we can detect the new one
    before = set(glob.glob(os.path.join(download_dir, "*.csv")))

    driver = _build_driver(download_dir)
    wait   = WebDriverWait(driver, WAIT_TIMEOUT)

    try:
        logger.info("Navigating to %s", comp_url)
        driver.get(comp_url)

        # Click the main Export button
        logger.info("Waiting for export button...")
        export_btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.export-button"))
        )
        export_btn.click()
        logger.info("Export button clicked.")

        # Wait for the export modal
        logger.info("Waiting for export modal...")
        wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".export-results-modal"))
        )
        logger.info("Modal visible.")

        # Click the Export button inside the modal
        modal_export = wait.until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//div[contains(@class,'export-results-modal')]"
                "//button[normalize-space()='Export' or contains(.,'Export')]",
            ))
        )
        driver.execute_script("arguments[0].click();", modal_export)
        logger.info("Modal export button clicked, waiting for CSV...")

        csv_path = _wait_for_new_csv(download_dir, before)
        logger.info("Downloaded: %s", csv_path)
        return csv_path

    finally:
        driver.quit()