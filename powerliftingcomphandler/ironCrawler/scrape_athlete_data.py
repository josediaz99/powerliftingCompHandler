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
from .scrape_competition_data import create_webdriver
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

def get_athlete_data(file_path:str) -> list:
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
        # still downloading?
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

if __name__ == "__main__":
    test_url = "https://liftingcast.com/meets/m3vj5jy9paz9/results"
    path = get_athlete_csv(test_url)
    athletes = get_athlete_data(path)

    for athlete in athletes:
        print(athlete)
    remove_csv(path)