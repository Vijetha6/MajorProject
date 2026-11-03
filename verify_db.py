import sqlite3
from pathlib import Path

db = Path("medicine_inventory.db")
conn = sqlite3.connect(db)
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables in DB:", [t[0] for t in tables])

# Check prescriptions schema
cols = conn.execute("PRAGMA table_info(prescriptions)").fetchall()
print("prescriptions columns:", [c[1] for c in cols])
conn.close()
