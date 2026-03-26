'''
this file contains the functions to clean and extract athlete information depending on need

- csv_to_list: this functions reads a csv file and extracts data as a list for further processing
- get_athlete_data: main function to extract athlete data as competition progresses
'''

import csv
import time
import glob
import os
from pathlib import Path
# web scraping + selenium specific libraires
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# custom modules
from scrape_competition_data import create_webdriver
####################################### HELPER FUNCTIONS ############################################

def clean_athlete_csv(file_path: str) -> list:
    """this function reads and cleans csv data to return athlete information

    Args:
        file_path (str): the file path to the csv file 
    Returns:
        header (list): csv headers/column names,
        athletes_list (list): a list containing a cleaned athlete list for futher processing
    """

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        raw_athletes = list(reader)

    cleaned_athletes = []
    for athlete in raw_athletes:
        # clean data from white space, quotes, and lowercase for easier processing
        cleaned_athletes.append([item.strip()
                                 .replace('"', '')
                                 .replace("'", '')
                                 .lower() for item in athlete])

    header = cleaned_athletes[0]
    return header, cleaned_athletes[1:]

def get_athlete_data(file_path:str) -> list:
    """function converts cleaned athlete csv to a list of athlete dicts

    Args:
        file_path (str): file path to csv containing athlete data

    Returns:
        athletes_list: list of athlete dictionaries
    """

    header, athletes = clean_athlete_csv(file_path)
    athletes_list = [dict(zip(header, athlete)) for athlete in athletes]

    return athletes_list

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
    file_path = Path(csv_path)
    file_path.unlink(missing_ok=True)
################################### MAIN ATHLETE DATA FUNCTIONS ####################################

def get_athlete_csv(link: str):
    driver = create_webdriver()
    download_dir = os.path.abspath(os.path.join(os.getcwd(), "data"))
    # snapshot existing csv files before starting
    before = set(glob.glob(os.path.join(download_dir, "*.csv")))

    wait = WebDriverWait(driver, 20)
    # navigate to page
    driver.get(link)
    # click into main export button
    export_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.export-button")))
    export_btn.click()
    # wait for modal to appear
    modal = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".export-results-modal")))
    # clicking modal
    modal_export = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            "//div[contains(@class,'export-results-modal')]//button[normalize-space()='Export' or contains(., 'Export')]"
        )))
    driver.execute_script("arguments[0].click();", modal_export)

    # waiting for csv to download
    csv_path = wait_for_new_csv(download_dir, before, timeout=120)
    # quiting driver
    driver.quit()
    return csv_path

if __name__ == "__main__":
    test_url = "https://liftingcast.com/meets/m3vj5jy9paz9/results"
    path = get_athlete_csv(test_url)
    athletes = get_athlete_data(path)

    for athlete in athletes:
        print(athlete)
    remove_csv(path)