"""
Pharmacy Network Data Import

Loads the CMS pharmacy network pipe-delimited files into the existing
cms_benefits.db SQLite database. Only loads the columns we need for
in-network / preferred lookups:

  pharmacy_network(
    contract_id, plan_id, segment_id,
    pharmacy_number, pharmacy_zipcode,
    preferred_status_retail, preferred_status_mail,
    pharmacy_retail, pharmacy_mail, in_area_flag
  )

Usage:
    python pharmacy_import.py [--cms-dir PATH] [--db PATH]

    Default cms-dir: ./Pdfs/CMS
    Default db: ./cms_benefits.db
"""

import sqlite3
import csv
import os
import sys
import time
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Columns we want to keep (subset of the full 19-column file)
KEEP_COLS = {
    "CONTRACT_ID", "PLAN_ID", "SEGMENT_ID",
    "PHARMACY_NUMBER", "PHARMACY_ZIPCODE",
    "PREFERRED_STATUS_RETAIL", "PREFERRED_STATUS_MAIL",
    "PHARMACY_RETAIL", "PHARMACY_MAIL", "IN_AREA_FLAG",
}

TABLE_NAME = "pharmacy_network"

# Relative paths to the 6 pharmacy network part files
PHARMACY_FILES = [
    "Monthly Prescription Drug Plan Formulary and Pharmacy Network Information"
    "/2026_20260122/pharmacy networks file  20260131 part 1.txt",
    "Monthly Prescription Drug Plan Formulary and Pharmacy Network Information"
    "/2026_20260122/pharmacy networks file  20260131 part 2.txt",
    "Monthly Prescription Drug Plan Formulary and Pharmacy Network Information"
    "/2026_20260122/pharmacy networks file  20260131 part 3.txt",
    "Monthly Prescription Drug Plan Formulary and Pharmacy Network Information"
    "/2026_20260122/pharmacy networks file  20260131 part 4.txt",
    "Monthly Prescription Drug Plan Formulary and Pharmacy Network Information"
    "/2026_20260122/pharmacy networks file  20260131 part 5.txt",
    "Monthly Prescription Drug Plan Formulary and Pharmacy Network Information"
    "/2026_20260122/pharmacy networks file  20260131 part 6.txt",
]


def run_import(cms_dir: str, db_path: str):
    """Import pharmacy network files into SQLite."""
    start = time.time()

    log.info("Pharmacy Network Import")
    log.info(f"  Source: {cms_dir}")
    log.info(f"  Database: {db_path}")
    log.info("")

    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA cache_size=-128000")  # 128MB cache for large imports

    # Drop and recreate table
    db.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    db.execute(f"""
        CREATE TABLE {TABLE_NAME} (
            contract_id TEXT,
            plan_id TEXT,
            segment_id TEXT,
            pharmacy_number TEXT,
            pharmacy_zipcode TEXT,
            preferred_status_retail TEXT,
            preferred_status_mail TEXT,
            pharmacy_retail TEXT,
            pharmacy_mail TEXT,
            in_area_flag TEXT
        )
    """)

    insert_sql = f"""
        INSERT INTO {TABLE_NAME} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    total_rows = 0

    for rel_path in PHARMACY_FILES:
        filepath = os.path.join(cms_dir, rel_path)
        if not os.path.isfile(filepath):
            log.warning(f"SKIP: {filepath} not found")
            continue

        fname = os.path.basename(filepath)
        log.info(f"Loading {fname}...")

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter="|")
            headers = [h.strip().upper() for h in next(reader)]

            # Find column indices for the columns we want
            col_indices = []
            for col in [
                "CONTRACT_ID", "PLAN_ID", "SEGMENT_ID",
                "PHARMACY_NUMBER", "PHARMACY_ZIPCODE",
                "PREFERRED_STATUS_RETAIL", "PREFERRED_STATUS_MAIL",
                "PHARMACY_RETAIL", "PHARMACY_MAIL", "IN_AREA_FLAG",
            ]:
                try:
                    col_indices.append(headers.index(col))
                except ValueError:
                    log.error(f"Column {col} not found in {fname}. Headers: {headers}")
                    break
            else:
                # All columns found, proceed with loading
                batch = []
                file_count = 0
                batch_size = 50000

                for row in reader:
                    try:
                        extracted = tuple(row[i].strip() for i in col_indices)
                        batch.append(extracted)
                        file_count += 1

                        if len(batch) >= batch_size:
                            db.executemany(insert_sql, batch)
                            batch = []
                            if file_count % 1000000 == 0:
                                log.info(f"  {fname}: {file_count:,} rows...")
                    except (IndexError, KeyError):
                        continue  # Skip malformed rows

                if batch:
                    db.executemany(insert_sql, batch)

                db.commit()
                total_rows += file_count
                log.info(f"  {fname}: {file_count:,} rows loaded")

    # Create indexes for fast lookups
    log.info("")
    log.info("Creating indexes...")
    db.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_pn_contract_plan
        ON {TABLE_NAME} (contract_id, plan_id)
    """)
    db.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_pn_zip
        ON {TABLE_NAME} (pharmacy_zipcode)
    """)
    db.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_pn_contract_plan_zip
        ON {TABLE_NAME} (contract_id, plan_id, pharmacy_zipcode)
    """)
    db.commit()
    log.info("  Indexes created")

    elapsed = time.time() - start
    db_size = os.path.getsize(db_path) / (1024 * 1024)

    log.info("")
    log.info(f"✓ Pharmacy import complete")
    log.info(f"  Total rows: {total_rows:,}")
    log.info(f"  Database size: {db_size:.1f} MB")
    log.info(f"  Time: {elapsed:.1f}s")

    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pharmacy Network Import")
    parser.add_argument("--cms-dir", default="Pdfs/CMS",
                        help="Path to CMS data directory")
    parser.add_argument("--db", default="cms_benefits.db",
                        help="SQLite database path")
    args = parser.parse_args()

    run_import(args.cms_dir, args.db)
