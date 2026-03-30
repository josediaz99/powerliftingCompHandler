'''
ironCrawler/scrape_athlete_data.py

scrapes and cleans athlete data from csv exports on lifting cast competitions
Run via: python manage.py scrape_athlete_data
'''

import csv
import glob
import os
import time
from pathlib import Path
# web scraping + selenium specific libraires
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# custom modules
from .create_selenium_driver import create_webdriver
# django
from .models import Athlete, Competition
####################################### HELPER FUNCTIONS ############################################

def clean_athlete_csv(file_path: str) -> list:
    """reads csv and returns a cleaned list of headers and athlete data

    Args:
        file_path (str): the file path to the csv file 
    Returns:
        (header, athletes_list) where header is a list of column names
        and athletes_list is a list of cleaned value rows.
    """

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        raw_athletes = list(reader)

    cleaned_athletes = []
    for athlete in raw_athletes:
        cleaned_athletes.append([item.strip()
                                 .replace('"', '')
                                 .replace("'", '')
                                 .lower() 
                                 for item in athlete])
        
    header = cleaned_athletes[0]
    return header, cleaned_athletes[1:]

def athlete_data_to_dicts(file_path:str) -> list:
    """converts cleaned athlete csv to a list of athlete dicts

    Args:
        file_path (str): file path to csv containing athlete data

    Returns:
        athletes_list: list of athlete dictionaries
    """

    header, athletes = clean_athlete_csv(file_path)
    return [dict(zip(header, athlete)) for athlete in athletes]

def wait_for_new_csv(download_dir: str, before_files: set[str], timeout: int = 90) -> str:
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

def remove_csv(csv_path: str):
    """helper function to remove csv file after processing

    Args:
        csv_path (str): file path to csv file to be removed
    """
    Path(csv_path).unlink(missing_ok=True)

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
        }
        
        # Handle age - convert to int if possible
        age_str = athlete_dict.get('age', '').strip()
        if age_str and age_str.isdigit():
            athlete_data['age'] = int(age_str)
        
        # Create or update athlete (assuming unique by name and competition)
        Athlete.objects.get_or_create(
            competition=competition,
            athlete_name=athlete_data['athlete_name'],
            defaults=athlete_data
        )
################################### MAIN ATHLETE DATA FUNCTIONS ####################################

def get_athlete_csv(link: str):
    driver = create_webdriver()
    download_dir = os.path.abspath(os.path.join(os.getcwd(), "data"))
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

    csv_path = wait_for_new_csv(download_dir, before, timeout=120)
    driver.quit()
    return csv_path

def scrape_and_save_athletes(competition: Competition):
    """Scrapes athlete data from a competition URL and saves to database.

    Args:
        competition (Competition): The competition to scrape athletes for.
    """
    try:
        csv_path = get_athlete_csv(competition.comp_url)
        athletes_data = athlete_data_to_dicts(csv_path)
        save_athletes_to_db(competition, athletes_data)
        remove_csv(csv_path)
        return len(athletes_data)
    except Exception as e:
        print(f"Error scraping athletes for {competition}: {e}")
        return 0

if __name__ == "__main__":
    test_url = "https://liftingcast.com/meets/m3vj5jy9paz9/results"
    path = get_athlete_csv(test_url)
    athletes = athlete_data_to_dicts(path)
    for athlete in athletes:
        print(athlete)
    remove_csv(path)