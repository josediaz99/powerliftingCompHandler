"""this file contains the functions to extract competition data from lifting cast
"""
# standard libraries
from datetime import datetime, timedelta
import os
import random
import re
import sys
from pathlib import Path
sys.path.append(str(Path().resolve().parent))
# web scraping + selenium specific libraires
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

##################################### HELPER FUNCTIONS #####################################

def parse_mmddyyyy(value) -> datetime.date:
    """
    Accepts: '02/26/2026', '2/6/2026', or None/''.
    Returns: datetime.date or None
    """
    if value is None:
        return None

    s = str(value).strip()
    if not s:
        return None

    # Normalize any separators like 02-26-2026 -> 02/26/2026
    s = re.sub(r"[-.]", "/", s)

    # Strict parse (month/day/year)
    try:
        return datetime.strptime(s, "%m/%d/%Y").date()
    except ValueError:
        return None  # or raise, depending on how strict you want it

def to_iso_date(value) -> datetime.date:
    """Returns 'YYYY-MM-DD' or None"""
    d = parse_mmddyyyy(value)
    return d.isoformat() if d else None

def date_in_days(days:int):
    '''
    using datetime and delta we calculate the future date from the number of days were looking for
    '''
    return (datetime.today() + timedelta(days=days)).date()

def parse_competitions(competition_table_rows: list)-> list:
    """function takes 

    Args:
        competition_table_rows (list): list of html rows containing competition data

    Returns:
        list: list of dictionaries containing competition data
    """
    url = "https://liftingcast.com"

    date_range = 7
    last_date = date_in_days(date_range)

    compe_list = []
    for competition in competition_table_rows:
        try:
            # seporating row into its table data components
            tds = competition.find_all('td')
            # extract data from each row
            link = tds[0].a.get('href')
            name = tds[0].a.contents[0]
            raw_date = tds[1].contents[0]
            date = datetime.strptime(raw_date, "%m/%d/%Y").date()

            # converting date to sqlite compatible version
            formated_date = to_iso_date(raw_date)

            # check if data is within the 7 days
            if  date <= last_date:
                comp = {'name':name,
                        'link':url + link,
                        'date':formated_date}
                compe_list.append(comp)
            else:
                break
        except :
            print("ERROR row data:", competition)
            break
    return compe_list

def get_random_user() -> str:
    """function avoid detection through returning randomized user agent

    Returns:
        str: a random user agent string
    """
    base = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    user_agent = [
    # Chrome 120+ Windows
    "Chrome/121.0.0.0 Safari/537.36",
    "Chrome/122.0.0.0 Safari/537.36",
    "Chrome/123.0.0.0 Safari/537.36",]    
    user = base + random.choice(user_agent)
    return user
###################################### MAIN SCRAPER FUNCTIONS ######################################

def create_webdriver() -> webdriver.Chrome:
    """function creates a selenium driver for user to scrape dynamic content
    Returns:
       driver (webdriver.chrome): a selenium webdriver for scraping dynamic content
    """

    user_agent = get_random_user()
    # create folder to store competition data
    download_dir = os.path.abspath(os.path.join(os.getcwd(), "data"))
    os.makedirs(download_dir, exist_ok=True)
    print("Current working directory:", os.getcwd())
    print("Download directory:", download_dir)
    print("Directory exists:", os.path.exists(download_dir))

    # pulls driver to avoid downloading manualy
    options = Options()

    # headless driver + reliability
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(f"--user-agent={user_agent}")

    # allowing for downloads early
    options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })

    # creating chrome driver
    driver = webdriver.Chrome(options=options)

    # remove webdriver flag
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    # allow headless downloads
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": download_dir
    })

    return driver

def get_html(driver) -> list:
    """function uses chrome driver to get html source code of lifting cast main page

    Args:
        driver (chrome.driver): selenium chrome driver

    Returns:
        str: html source code of the page
    """
    wait_time = 60
    wait = WebDriverWait(driver, wait_time)

    # using the driver we automate and scrape the lifting cast competition page
    url = "https://liftingcast.com"
    driver.get(url=url)

    # wait for the table to exists with rows
    comp_row = "div.meets-table-table-wrapper table.table tbody tr"
    comp_links = "div.meets-table-table-wrapper table.table a[href]"
    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, comp_row)))
    # wait for the table to be populated
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, comp_links)) >= 5)

    # store out html, parse, and store as rows of competitions
    html = driver.page_source
    driver.quit()
    return html

def get_competition_data() -> list:
    """function initializes web driver to retrieve html and parse for competition data to return
    a list of competitions within the next 7 days

    Returns:
        competition_list: competition list of dicts with name, link and date
    """

    html = get_html(create_webdriver())
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr')

    # remove the first 2 rows (not competition data)
    rows = rows[2:]
    competition_list = parse_competitions(rows)

    return competition_list

if __name__ == "__main__":
    comps = get_competition_data()
    for comp in comps:
        print(comp)
