import sqlite3
from pathlib import Path

DB_PATH = Path("mystic.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS warns (
        user_id INTEGER,
        chat_id INTEGER,
        count INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, chat_id)
    )""")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()