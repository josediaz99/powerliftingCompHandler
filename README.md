# IronCrawler — powerliftingCompHandler

## Project goal

Give a less experienced competitor, or a coach handling many athletes, the tools to make better decisions in the one minute they are allowed to declare an attempt. The data is readily available on [LiftingCast](https://liftingcast.com), but without a handler, or while tracking several athletes at once, it is overwhelming.

IronCrawler collects upcoming and live meets from LiftingCast, keeps their athlete data current, and shows each athlete where they stand against the lifters they are actually competing with.

---

## What the app does

| Page | URL | What it shows |
|---|---|---|
| Meets | `/` | The meets an admin has selected for scraping, with a "today / tomorrow / in N days" chip worked out from the viewer's own local date |
| Admin login | `/login/` | Sign-in for staff accounts |
| Manage meets | `/manage/` | Admins only: the scrape list and the meets not on it, with buttons to add and remove meets |
| Select athlete | `/athlete_select/<comp_id>/` | The meet's roster, filterable by gender, weight class, division and category, sortable by total, DOTS or name |
| Athlete dashboard | `/athlete_dash/<athlete_id>/` | The athlete's total and DOTS, their rank and gap to first place, and a leaderboard with a lift-by-lift comparison against any competitor |

On the dashboard:

- **Rank by DOTS** compares everyone of the same gender; the **Compare** checkboxes narrow that to the same weight class and/or category.
- **Rank by Total** always compares within the athlete's weight class.
- Opening a competitor shows squat, bench, subtotal (squat + bench), deadlift, total and DOTS side by side, so the deadlift needed is easy to work out.
- The back link stays pinned at the top. With the screen held horizontally, only the leaderboard list scrolls.
- The page updates itself every 30 seconds from `/athlete_dash/<athlete_id>/data/`. There is no manual refresh.

### Choosing which meets are scraped

Every meet LiftingCast lists is stored, but athletes are only scraped for meets an admin has added to the scrape list at `/manage/`. New meets start off the list.

The manage page shows two lists, each sorted by date: the scrape list, and the meets not on it. The **+** button moves a meet onto the scrape list and the **−** button moves it back; each change is confirmed on screen. The scrape list is on the left and the available meets on the right; on a screen too narrow for two columns they stack with the scrape list on top.

Removing a meet stops its scraping and hides it from the Meets page; athletes already stored are kept. A meet that has been added is scraped at the next full sync (within 3 hours), or within a minute if it is already live.

Admins are Django staff accounts. Create one with:

```bash
python manage.py createsuperuser
```

Staff accounts can also be managed, and meets added or removed in bulk, in the Django admin at `/admin/`.

---

## How it works

```
liftingcast.com
   │  home page (meets table)            │  each meet's "Export" CSV
   ▼                                     ▼
scrape_competition_data.py        scrape_athlete_data.py
   │                                     │
   └──────────► scraper.py ◄─────────────┘        live_refresh.py
              full sync, every 3 hours            live meets, every minute
                     │                                   │
                     └────────────► SQLite ◄─────────────┘
                                      │
                               Django views + templates
```

### Full sync (every 3 hours)

`scrape_and_load()` in `scraper.py`:

1. Loads the LiftingCast home page and reads every meet dated today through the next 7 days.
2. Creates meets that are new and removes meets that are no longer listed. If the page returns no meets at all, nothing is removed.
3. Scrapes the athletes of each meet selected for scraping in up to 4 parallel browsers, then writes them to the database one meet at a time.

Saving a meet's athletes creates or updates everyone in the export and removes anyone who is no longer in it (withdrawn).

### Live refresh (every minute)

`live_refresh.py` keeps selected meets that have begun up to date:

- A meet is treated as live while its date is "today" in any time zone, because meets are stored with a date but no time zone.
- Up to 4 browsers stay open between passes. Starting Chrome takes about 8 seconds, while a browser that is already open scrapes a meet in about 2.5 seconds. Measured: 39 meets in about 27 seconds.
- A meet whose export is identical to the last one saved is not written again.
- A pass stops starting new scrapes after 50 seconds. Meets it did not reach go first on the next pass.
- When the scheduler is running, the 3-hour full sync leaves live meets to the live refresh.

---

## Getting started

Requirements: Python 3.12+ and Google Chrome (Selenium downloads the matching driver itself).

```bash
git clone https://github.com/josediaz99/powerliftingCompHandler.git
cd powerliftingCompHandler

python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser        # the admin account used at /login/
python manage.py scrape_competitions    # loads the list of meets
python manage.py runserver
```

Then open http://127.0.0.1:8000/, log in through the **Admin** link and add the meets to scrape to the scrape list.

To keep the data current, run the scheduler in a second terminal:

```bash
python manage.py run_scheduler
```

### Commands

| Command | What it does |
|---|---|
| `python manage.py createsuperuser` | Creates an admin account |
| `python manage.py scrape_competitions` | One full sync: meets for the next 7 days, and the athletes of the selected meets |
| `python manage.py scrape_athletes` | Re-scrapes athletes for the selected meets |
| `python manage.py run_scheduler` | Runs until stopped: full sync every 3 hours, live refresh every minute |
| `python manage.py runserver` | Serves the web app |
| `python manage.py test ironCrawler` | Runs the test suite |

---

## Project layout

```
manage.py
requirements.txt
powerliftingcomphandler/          Django project: settings, root urls, wsgi/asgi
ironCrawler/                      the app
  models.py                       Competition, Athlete
  views.py                        meets list, athlete select, dashboard, dashboard data (JSON), manage meets
  urls.py                         app routes, plus login/logout
  templates/ironCrawler/          index.html, athlete_select.html, athlete_dash.html, login.html, manage_competitions.html
  static/ironCrawler/             style.css, countdown.js
  management/commands/            scrape_competitions, scrape_athletes, run_scheduler
  webscraping/
    create_selenium_driver.py     headless Chrome set up for downloads
    scrape_competition_data.py    LiftingCast home page -> upcoming meets
    scrape_athlete_data.py        meet CSV export -> cleaned athletes -> database
    scraper.py                    scrape_and_load(): the full sync
    live_refresh.py               every-minute refresh with a pool of reused browsers
  tests/                          one test module per area
logs/                             scraper.log, scheduler.log, scrape_failures.log
```

---

## Technical challenges solved

### Dynamic website rendering

LiftingCast is a client-side React app, so static scraping does not work. Selenium drives a headless Chrome and uses explicit waits so elements are ready before they are clicked. The meets table is then parsed with BeautifulSoup.

### Reliable file downloads

Athlete data comes from each meet's "Export" button, which downloads a CSV. The scraper:

- gives every browser its own download directory so parallel scrapes cannot collide
- waits for the CSV's own `.csv.crdownload` file to finish before reading it
- ignores an unrelated `downloads.htm.crdownload` that LiftingCast pages can leave behind for up to 30 seconds
- deletes the file once it has been read

### Reusing browsers

A browser tab that keeps loading LiftingCast meets hangs on the "LOADING" screen on every 7th page. A reused browser therefore opens each meet in a fresh tab and closes the previous one. A browser whose scrape fails is thrown away, so a late download can never be read as another meet's export.

### Irregular CSV data

The exports are formatted slightly differently between meets. Behaviour that has held across the meets observed so far:

- failed lifts are negative (e.g. `-200`); a negative "best" lift means every attempt failed, so it is stored as 0
- header names are the same across meets, except for optional 4th attempts, which do not count toward totals
- referee decisions can contain commas and stray quotes, so every value is trimmed, lowercased and stripped of `"` and `'`
- blank numbers are stored as 0; body weight and DOTS stay empty until they exist

### Retries and failure logging

A full-sync scrape that fails is retried once, then logged with its traceback to `logs/scrape_failures.log`. A live meet that fails three passes in a row is logged as an error.

---

## Testing

```bash
python manage.py test ironCrawler
```

The tests never start Chrome or contact LiftingCast: browser work is replaced with fakes, and CSV parsing runs against a sample in the LiftingCast export format. They cover CSV cleaning and field mapping, the download wait, withdrawn-athlete removal, the meets-table parser, the full sync, the live refresh and its browser pool, the scheduler jobs and the views.

---

## Tech stack

- Python, Django
- Selenium with headless Chrome, BeautifulSoup4
- APScheduler with django-apscheduler
- SQLite
- Django templates, plain JavaScript and CSS
