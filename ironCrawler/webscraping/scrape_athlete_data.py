'''
ironCrawler/webscraping/scrape_athlete_data.py

scrapes and cleans athlete data from csv exports on lifting cast competitions
Run via: python manage.py scrape_athletes
'''

import csv
import glob
import hashlib
import logging
import os
import shutil
import tempfile
import time

# web scraping + selenium specific libraires
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# django
from django.db import transaction

from ..models import Athlete, Competition

# custom modules
from .create_selenium_driver import create_webdriver

logger = logging.getLogger(__name__)

# total tries per competition before it is logged as a critical failure
SCRAPE_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 5
# live refresh runs every minute, so a slow export is abandoned quickly
LIVE_CSV_TIMEOUT_SECONDS = 30
####################################### HELPER FUNCTIONS ############################################

def _clean_athlete_csv(file_path: str) -> list:
    """reads csv and returns a cleaned list of headers and athlete data

    Args:
        file_path (str): the file path to the csv file 
    Returns:
        (header, athletes_list) where header is a list of column names
        and athletes_list is a list of cleaned value rows.
    """

    with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        raw_athletes = list(reader)

    cleaned_athletes = []
    for athlete in raw_athletes:
        cleaned_athletes.append([item.strip()
                                 .replace('"', '')
                                 .replace("'", '')
                                 .lower() 
                                 for item in athlete])
        
    if not cleaned_athletes:
        return [], []

    header = cleaned_athletes[0]
    return header, cleaned_athletes[1:]

def _athlete_data_to_dicts(file_path:str) -> list:
    """converts cleaned athlete csv to a list of athlete dicts

    Args:
        file_path (str): file path to csv containing athlete data

    Returns:
        athletes_list: list of athlete dictionaries
    """

    header, athletes = _clean_athlete_csv(file_path)
    return [dict(zip(header, athlete)) for athlete in athletes]

def _wait_for_new_csv(download_dir: str, before_files: set[str], timeout: int = 90) -> str:
    end = time.time() + timeout
    while time.time() < end:
        # if still downloading (only the csv matters: liftingcast pages can leave an
        # unrelated "downloads.htm.crdownload" behind that takes up to 30s to clear)
        if glob.glob(os.path.join(download_dir, "*.csv.crdownload")):
            time.sleep(0.5)
            continue

        current = set(glob.glob(os.path.join(download_dir, "*.csv")))
        new_files = current - before_files
        if new_files:
            return max(new_files, key=os.path.getmtime)

        time.sleep(0.5)

    raise TimeoutError("CSV download did not complete in time.")

def _to_float(value: str) -> float:
    """Converts a CSV numeric field to a float, treating blanks/dashes as 0."""
    value = (value or '').strip()
    if not value or value == '-':
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0

def _to_best_lift(value: str) -> float:
    """Converts a 'Best Squat/Bench/Deadlift' CSV field to a float.

    A negative value means every attempt for that lift was failed, so it
    counts as no successful lift (0kg).
    """
    return max(0.0, _to_float(value))

def _remove_withdrawn_athletes(competition: Competition, scraped_names: set) -> int:
    """Deletes athletes stored for a competition that are missing from the latest scrape.

    Args:
        competition (Competition): The competition whose roster was just scraped.
        scraped_names (set): athlete names present in the latest scrape.

    Returns:
        int: number of athletes removed
    """
    # an empty scrape is far more likely a bad export than a meet with no lifters
    if not scraped_names:
        logger.warning("No athletes scraped for %s — skipping withdrawn-athlete removal", competition)
        return 0

    withdrawn = Athlete.objects.filter(competition=competition).exclude(athlete_name__in=scraped_names)
    removed_names = list(withdrawn.values_list('athlete_name', flat=True))
    if not removed_names:
        return 0

    withdrawn.delete()
    for name in removed_names:
        logger.info("  [removed withdrawn] %s — %s", competition, name)
    return len(removed_names)

@transaction.atomic
def save_athletes_to_db(competition: Competition, athletes_data: list) -> int:
    """Syncs a competition's athletes with the database from a list of athlete dictionaries.

    Athletes in the list are created or updated; athletes already stored for the
    competition but missing from the list (withdrawn) are removed.

    Args:
        competition (Competition): The competition instance to link athletes to.
        athletes_data (list): List of dictionaries containing athlete data.

    Returns:
        int: number of withdrawn athletes removed
    """
    scraped_names = set()
    for athlete_dict in athletes_data:
        # Map CSV fields to model fields
        athlete_data = {
            'competition': competition,
            'athlete_name': athlete_dict.get('name', '').strip(),
            'gender': athlete_dict.get('gender', '').strip().lower(),
            'category': athlete_dict.get('category', '').strip().lower(),
            'team': athlete_dict.get('team', '').strip(),
            'division': athlete_dict.get('awards division', '').strip(),
            'weight_class': athlete_dict.get('weight class', '').strip(),
            'body_weight': _to_float(athlete_dict.get('body weight (kg)', '')) or None,
            'best_squat': _to_best_lift(athlete_dict.get('best squat', '')),
            'best_bench': _to_best_lift(athlete_dict.get('best bench', '')),
            'best_deadlift': _to_best_lift(athlete_dict.get('best deadlift', '')),
            'total': _to_float(athlete_dict.get('total', '')),
            'dots_score': _to_float(athlete_dict.get('dots points', '')) or None,
        }

        # Handle age - convert to int if possible
        age_str = athlete_dict.get('age', '').strip()
        if age_str and age_str.isdigit():
            athlete_data['age'] = int(age_str)

        # Create or update athlete (assuming unique by name and competition)
        Athlete.objects.update_or_create(
            competition=competition,
            athlete_name=athlete_data['athlete_name'],
            defaults=athlete_data
        )
        scraped_names.add(athlete_data['athlete_name'])

    return _remove_withdrawn_athletes(competition, scraped_names)
################################### MAIN ATHLETE DATA FUNCTIONS ####################################

def _export_athlete_csv(driver, link: str, download_dir: str, csv_timeout: int = 120) -> str:
    """Navigates an existing webdriver to a competition page and downloads its CSV export.

    Args:
        driver (webdriver.Chrome): a running driver whose downloads go to download_dir
        link (str): competition URL on liftingcast.com
        download_dir (str): directory the driver downloads into
        csv_timeout (int): seconds to wait for the download to finish

    Returns:
        str: path to the downloaded CSV file
    """
    # snapshot existing csv files before starting
    before = set(glob.glob(os.path.join(download_dir, "*.csv")))

    wait = WebDriverWait(driver, 20)
    driver.get(link)

    export_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.export-button")))
    export_btn.click()

    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".export-results-modal")))
    # clicking modal
    modal_export = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            "//div[contains(@class,'export-results-modal')]//button[normalize-space()='Export' or contains(., 'Export')]"
        )))
    driver.execute_script("arguments[0].click();", modal_export)

    return _wait_for_new_csv(download_dir, before, timeout=csv_timeout)

def _get_athlete_csv(link: str, download_dir: str = None):
    """Uses a webdriver to navigate to a competition page and download its CSV export.

    Args:
        link (str): competition URL on liftingcast.com
        download_dir (str): directory for the downloaded CSV. Each concurrent caller
            should pass its own isolated temp directory to avoid file collisions.

    Returns:
        str: path to the downloaded CSV file
    """
    if download_dir is None:
        download_dir = os.path.abspath(os.path.join(os.getcwd(), "data"))
    driver = create_webdriver(download_dir)
    try:
        return _export_athlete_csv(driver, link, download_dir)
    finally:
        driver.quit()

def _open_fresh_tab(driver, download_dir: str):
    """Replaces the driver's current tab with a new one that downloads into download_dir.

    A tab that keeps loading liftingcast pages hangs on the "LOADING" screen on
    every 7th page, so a reused driver loads each competition in its own tab.
    """
    old_tab = driver.current_window_handle
    driver.switch_to.new_window("tab")
    new_tab = driver.current_window_handle
    driver.switch_to.window(old_tab)
    driver.close()
    driver.switch_to.window(new_tab)
    # download behaviour is set per tab
    driver.execute_cdp_cmd("Page.setDownloadBehavior",
                           {"behavior": "allow",
                            "downloadPath": download_dir})

def scrape_athletes_with_driver(driver, competition: Competition, download_dir: str) -> tuple:
    """Scrapes one competition's athletes with an already-running driver.

    Used by the live refresh, which keeps drivers open between scrapes to avoid
    paying Chrome's startup cost per competition. Safe to call from worker
    threads — no database access. Raises on failure.

    Args:
        driver (webdriver.Chrome): a running driver whose downloads go to download_dir
        competition (Competition): The competition to scrape athletes for.
        download_dir (str): directory the driver downloads into

    Returns:
        (digest, athletes_data) where digest is a hash of the raw CSV, used to
        tell whether anything changed since the previous scrape.
    """
    _open_fresh_tab(driver, download_dir)
    csv_path = _export_athlete_csv(driver, competition.comp_url, download_dir,
                                   csv_timeout=LIVE_CSV_TIMEOUT_SECONDS)
    try:
        with open(csv_path, 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        return digest, _athlete_data_to_dicts(csv_path)
    finally:
        os.remove(csv_path)

def _scrape_athletes_once(competition: Competition) -> list:
    """Single scrape attempt in its own temp download directory. Raises on failure."""
    download_dir = tempfile.mkdtemp(prefix="lc_athlete_")
    try:
        csv_path = _get_athlete_csv(competition.comp_url, download_dir)
        return _athlete_data_to_dicts(csv_path)
    finally:
        shutil.rmtree(download_dir, ignore_errors=True)

def scrape_athletes_only(competition: Competition, attempts: int = SCRAPE_ATTEMPTS) -> tuple:
    """Scrapes athlete data from a competition URL and returns it without touching the DB.

    Safe to call from worker threads — no database access. A failed scrape is
    retried (up to `attempts` total); a competition that fails every attempt is
    logged at CRITICAL with the full traceback so it can be investigated.

    Args:
        competition (Competition): The competition to scrape athletes for.
        attempts (int): total number of tries before giving up.

    Returns:
        (competition, athletes_data, error) where error is None on success or
        an error message string on failure (athletes_data will be []).
    """
    logger.info("Scraping athletes for: %s", competition)

    for attempt in range(1, attempts + 1):
        try:
            athletes_data = _scrape_athletes_once(competition)
            if attempt > 1:
                logger.info("Scrape succeeded for %s on attempt %d/%d", competition, attempt, attempts)
            return competition, athletes_data, None
        except Exception as e:
            if attempt < attempts:
                logger.warning("Scrape attempt %d/%d failed for %s: %s — retrying in %ds",
                               attempt, attempts, competition, e, RETRY_DELAY_SECONDS)
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.critical(
                    "SCRAPE FAILED after %d attempts — investigate: %s | url=%s | %s: %s",
                    attempts, competition, competition.comp_url, type(e).__name__, e,
                    exc_info=True,
                )
                return competition, [], f"{type(e).__name__}: {e}"

def scrape_and_save_athletes(competition: Competition) -> int:
    """Scrapes athlete data for a competition and saves it to the database.

    Not thread safe (writes to the DB) — use scrape_athletes_only from worker threads.

    Args:
        competition (Competition): The competition to scrape athletes for.

    Returns:
        int: number of athletes saved (0 if the scrape failed)
    """
    _, athletes_data, error = scrape_athletes_only(competition)
    if error:
        return 0
    save_athletes_to_db(competition, athletes_data)
    return len(athletes_data)
