import sqlite3
from pathlib import Path

DB_NAME = "IronCrawler.db"

COMPETITION_SCHEMA = """
CREATE TABLE IF NOT EXISTS competitions (
    comp_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    comp_name TEXT NOT NULL,
    comp_url  TEXT NOT NULL,
    comp_date TEXT NOT NULL,   -- ISO: YYYY-MM-DD

    UNIQUE (comp_name, comp_date)
);
"""

ATHLETE_SCHEMA = """
CREATE TABLE IF NOT EXISTS athletes (
    athlete_name TEXT
    gender TEXT CHECK(gender IN ('male', 'female'))  
    category TEXT
    team TEXT      
    session TEXT
    flight TEXT
    division TEXT    
    bw INTEGER
    weight_class TEXT
    age INTEGER
    best_squat INTEGER
    best_bench INTEGER
    best_dead INTEGER
);
"""
def init_db(db_path: str = DB_NAME) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # establish connection to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # important PRAGMAs
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")

    # create tables
    with conn:
        conn.executescript(COMPETITION_SCHEMA)
    return conn

if __name__ == "__main__":
    conn = init_db()