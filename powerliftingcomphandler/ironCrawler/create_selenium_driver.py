"""
ironCrawler/web_driver.py

Contains helper functions for creating and configuring selenium webdrivers for 
data wrangling and downloading from dynamic content.
"""
import random
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

############################# HELPER FUNCTIONS ############################################
def get_random_user() -> str:
    """returns a randomized user agent as a string for selenium driver

    Returns:
        str: a random user agent string
    """
    base = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    user_agent = [ # Chrome 120+ Windows
        "Chrome/121.0.0.0 Safari/537.36",
        "Chrome/122.0.0.0 Safari/537.36",
        "Chrome/123.0.0.0 Safari/537.36",]
    
    user = base + random.choice(user_agent)
    return user

############################# MAIN WEB DRIVER FUNCTIONS ######################################
def create_webdriver() -> webdriver.Chrome:
    """function creates a selenium driver for user to scrape dynamic content
    Returns:
       driver (webdriver.chrome): a selenium webdriver for scraping dynamic content
    """

    user_agent = get_random_user()

    # create folder to store competition data
    download_dir = os.path.abspath(os.path.join(os.getcwd(), "data"))
    os.makedirs(download_dir, exist_ok=True)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(f"--user-agent={user_agent}")
    options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })

    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    # allow headless downloads
    driver.execute_cdp_cmd( "Page.setDownloadBehavior",
                           {"behavior": "allow",
                            "downloadPath": download_dir})

    return driver
