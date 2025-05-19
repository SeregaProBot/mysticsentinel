import sqlite3

def init_db():
    conn = sqlite3.connect("mystic.db")
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS warns (
        user_id INTEGER,
        chat_id INTEGER,
        count INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, chat_id)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS blacklist (
        user_id INTEGER PRIMARY KEY,
        reason TEXT
    )""")
    
    conn.commit()
    conn.close()

init_db()