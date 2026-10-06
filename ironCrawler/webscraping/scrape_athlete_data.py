'''
ironCrawler/scrape_athlete_data.py

scrapes and cleans athlete data from csv exports on lifting cast competitions
Run via: python manage.py scrape_athlete_data
'''

import csv
import glob
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

# web scraping + selenium specific libraires
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# django
from ..models import Athlete, Competition

# custom modules
from .create_selenium_driver import create_webdriver

logger = logging.getLogger(__name__)

# total tries per competition before it is logged as a critical failure
SCRAPE_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 5
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
        # if still downloading
        if glob.glob(os.path.join(download_dir, "*.crdownload")):
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

def save_athletes_to_db(competition: Competition, athletes_data: list):
    """Saves a list of athlete dictionaries to the database, linked to the given competition.

    Args:
        competition (Competition): The competition instance to link athletes to.
        athletes_data (list): List of dictionaries containing athlete data.
    """
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
################################### MAIN ATHLETE DATA FUNCTIONS ####################################

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
    # snapshot existing csv files before starting
    before = set(glob.glob(os.path.join(download_dir, "*.csv")))

    try:
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

        return _wait_for_new_csv(download_dir, before, timeout=120)
    finally:
        driver.quit()

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
