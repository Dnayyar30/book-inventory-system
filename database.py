import sqlite3

DB="books.db"

def connect():
    return sqlite3.connect(DB)


def init():

    conn=connect()
    c=conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS books(
    id INTEGER PRIMARY KEY,
    name TEXT,
    class TEXT,
    vendor TEXT,
    purchase_price REAL,
    mrp REAL
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS schools(
    id INTEGER PRIMARY KEY,
    name TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS purchases(
    id INTEGER PRIMARY KEY,
    book_id INTEGER,
    vendor TEXT,
    qty INTEGER,
    price REAL,
    date TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS distribution(
    id INTEGER PRIMARY KEY,
    school_id INTEGER,
    book_id INTEGER,
    qty INTEGER,
    price REAL,
    date TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS sales(
    id INTEGER PRIMARY KEY,
    school_id INTEGER,
    book_id INTEGER,
    qty INTEGER,
    price REAL,
    student TEXT,
    date TEXT
    )
    """)

    conn.commit()
    conn.close()