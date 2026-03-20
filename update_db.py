import sqlite3

conn = sqlite3.connect("books.db")
c = conn.cursor()

c.execute("ALTER TABLE challans ADD COLUMN received_qty INTEGER DEFAULT 0")
c.execute("ALTER TABLE challans ADD COLUMN received_by TEXT")
c.execute("ALTER TABLE challans ADD COLUMN received_date TEXT")

conn.commit()
conn.close()

print("DONE ✅")