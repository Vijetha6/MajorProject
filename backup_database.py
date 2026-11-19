"""Make a safe, timestamped backup copy of the MedInfo SQLite databases.

Run this BEFORE starting the updated application for the first time:

    python backup_database.py

It never changes the original database files. Backups are saved in the
"db_backups" folder next to this script.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
BACKUP_DIR = BASE_DIR / "db_backups"
DATABASE_FILES = ("medicine_inventory.db", "doctor_records.db")


def backup_database(source: Path, backup_dir: Path = BACKUP_DIR) -> Path:
    """Copy one SQLite database using SQLite's own backup API (safe even if in use)."""
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"{source.stem}_{stamp}{source.suffix}"
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


if __name__ == "__main__":
    found = False
    for name in DATABASE_FILES:
        path = BASE_DIR / name
        if path.exists():
            print(f"Backed up {name} -> {backup_database(path)}")
            found = True
        else:
            print(f"Skipped {name}: file not found.")
    if not found:
        print("No database files found. Nothing to back up yet.")
