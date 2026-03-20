# **PROJECT GOAL**

    The goal is to provide a less experienced competitor or coach handling many athletes with the tools to make better decisions in the minute they are allowed to declare an attempt.The data is readily available on lifting cast, but without the help of a handler or while tracking multiple athletes, this information can be overwhelming

---

### Overview

    The repository demonstrates the full workflow from**proof-of-concept experimentation in Jupyter** to **modular, reusable scraping functions** designed for scalable data collection.

    Because LiftingCast renders results client side and exposes semi-structured athlete data, traditional static scraping approaches are insufficient. This project uses**Selenium-driven browser automation** to reliably interact with the UI, trigger exports, and collect athlete-level results

---

### **comp_scraping.ipynb & athlete_scraping.ipynb**

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

### **Production Scraper (currently working on)**

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

### Technical Challenges Solved

##### Dynamic Website Rendering

LiftingCast uses a client-side React interface. The scraper uses **explicit Selenium waits** to ensure elements are interactable before actions are performed.

##### Semi-Structured Athlete Data

Athlete information appears in grouped blocks with weight-class headers. The project includes logic to correctly associate athletes with their respective categories.

---

### Athlete Modeling and Missing-Field Reconstruction

The LiftingCast export CSVs are not always fully complete or consistently structured across meets. To standardize downstream analysis, this project includes an `athlete.py` domain model athlete.py that represents an athlete as an object and computes derived fields when they are missing or need to be calculated.

##### Purpose

Some of the data which seems to be available on the csv is calculated post competition and need a way to be calculated before making decision. The athlete model also provides a consistent way to:

* store athlete identity fields
* track best squat/bench/deadlift
* assign a weight class from bodyweight and sex using Powerlifting America-style class thresholds athlete
* compute GL points from bodyweight, total, and sex using configured coefficients athlete

## Tech Stack

* Python
* Selenium
* Jupyter Notebook
* pandas
* Chrome WebDriver
* BeautifulSoup4
