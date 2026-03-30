# **PROJECT GOAL**

    The goal is to provide a less experienced competitor or coach handling many athletes with the tools to make better decisions in the minute they are allowed to declare an attempt.The data is readily available on lifting cast, but without the help of a handler or while tracking multiple athletes, this information can be overwhelming

---

## Overview

    The repository demonstrates the full workflow from**proof-of-concept experimentation in Jupyter** to **modular, reusable scraping functions** designed for scalable data collection.

    Because LiftingCast renders results client side and exposes semi-structured athlete data, traditional static scraping approaches are insufficient. This project uses**Selenium-driven browser automation** to reliably interact with the UI, trigger exports, and collect athlete-level results

---

### **comp_scraping.ipynb & athlete_scraping.ipynb (webscraping branch)**

The notebooks demonstrates a proof of concept of scraping LiftingCast by:

* Launching Selenium with a configured download directory
* Navigating to a competition results page
* Handling dynamic React rendered content
* Opening the export modal
* Clicking the export button
* Waiting for the athlete CSV to fully download
* Validating the downloaded file

##### **Purpose of the ipynb files**

The notebooks exists to:

* Validate selectors and page behavior
* Reverse engineer the export workflow
* Handle timing and modal interactions
* Prototype download completion logic
* Reduce risk before productionizing

This step ensures the production scraper is built on verified browser automation behavior

### scrape_athlete_data, scrape_competition_data

After validating the workflow in the notebook, the logic is being refactored into reusable functions that will:

* Scale across many competitions
* Improve reliability and error handling
* Support batch data collection
* Enable downstream database ingestion

##### **Core Responsibilities**

The production modules will:

* Initialize and manage WebDriver sessions
* Navigate competition pages
* Handle dynamic UI elements
* Trigger and monitor exports
* Parse semi-structured athlete data
* Standardize outputs for analysis

##### Reliable File Downloads

The scraper implements filesystem monitoring to:

* Detect `.crdownload` temporary files
* Wait for download completion
* Prevent partial file reads
* Ensure deterministic pipeline behavior
* Remove files once ingested

### Technical Challenges Solved

##### Dynamic Website Rendering

LiftingCast uses a client-side React interface. The scraper uses **explicit Selenium waits** to ensure elements are interactable before actions are performed.

##### Semi-Structured competition data

Competition data is stored in dynamically redered components which were parsed using beautiful soup to be stored to database

##### Custom parsing logic for CSV irregularities

athlete data is stored in CSVs which are can be formatted slightly different between each competition. Through monitoring of behavior of data througout competitions there are few bahaviors implemented to competitions which make pulling the data simpler

- failed lifts will be negative (e.g -200)
- all headers contain the same header names excluding (4rth attempts)
  - 4rth attemps are not considered in competition to add to winning totals
- refferee decisions can contain , inside their values making cleaning data from ", ', and extra spaces necessary
- referee decisions can be usefull when considering creating a prediction model for future competition but not necessary when failed lifts are already stored as negative

---

### Tech Stack

* Python
* Django
* Selenium
* Jupyter Notebook
* pandas
* Chrome WebDriver
* BeautifulSoup4
* sqlite3
* html
* css

---

### Future implementation

-  data transformation and feature engineering for machine learning algorithms to predict if and how an athlete will fail a lift

---
