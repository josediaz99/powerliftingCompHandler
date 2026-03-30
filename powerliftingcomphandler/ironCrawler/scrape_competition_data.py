"""
ironCrawler/scrape_competition_data.py

scrapes upcoming competition data from lifting cast main page
Run via: python manage.py scrape_competition_data --url <meet url>
"""
# standard libraries
from datetime import datetime, timedelta
import re
# web scraping + selenium specific libraires
from bs4 import BeautifulSoup
from .create_selenium_driver import create_webdriver
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
    """function takes list of html table rows and extracts competition data as a lift of dicts

    Args:
        competition_table_rows (list): list of html rows containing competition data

    Returns:
        list: list of dictionaries containing competition data
    """
    base_url = "https://liftingcast.com"

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

            # check if data is within the 7 days
            if date >= datetime.today().date() and date <= last_date:
                comp = {'name': name,
                        'link': base_url + link,
                        'date': to_iso_date(raw_date)}
                compe_list.append(comp)
            else:
                break
        except Exception:
            print("ERROR row data:", competition)
            break
    return compe_list

###################################### MAIN SCRAPER FUNCTIONS ######################################

def get_html(driver) -> list:
    """function uses chrome driver to get html source code of lifting cast main page

    Args:
        driver (chrome.driver): selenium chrome driver

    Returns:
        str: html source code of the page
    """
    wait = WebDriverWait(driver, 60)
    url = "https://liftingcast.com"
    driver.get(url)

    comp_row = "div.meets-table-table-wrapper table.table tbody tr"
    comp_links = "div.meets-table-table-wrapper table.table a[href]"
    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, comp_row)))
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, comp_links)) >= 5)

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
    rows = soup.find_all('tr')[2:]# remove the first 2 rows (not competition data)

    return parse_competitions(rows)

if __name__ == "__main__":
    comps = get_competition_data()
    for comp in comps:
        print(comp)
