"""
CMS Data Import Pipeline
Loads Medicare Advantage plan data into SQLite for fast lookups.

Files loaded:
  Formulary PUF (pipe-delimited):
    - plan_formulary: Plan → Formulary ID bridge
    - formulary_drugs: Drug RXCUI/NDC → tier + restrictions
    - beneficiary_cost: Tier → copay amounts

  PBP Benefits (tab-delimited, UTF-16):
    - pbp_section_a: Plan name, org, phones, SNP type
    - pbp_section_d: Premium, Part B giveback, deductible, MOOP
    - pbp_b7_health_prof: PCP/specialist copays
    - pbp_b4_emerg_urgent: ER + urgent care copays
    - pbp_b16_dental: Dental preventive + comprehensive
    - pbp_b13_other_services: OTC allowance
    - pbp_b13i_ssbci: Flex card / SSBCI benefits

Usage:
    python cms_import.py [--cms-dir PATH] [--db PATH]

    Default cms-dir: ./pdfs/CMS
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

# ── File definitions ──────────────────────────────────────────────────────────
# Each entry: (table_name, relative_path, delimiter, encoding)

PUF_FILES = [
    (
        "plan_formulary",
        "Monthly Prescription Drug Plan Formulary and Pharmacy Network Information"
        "/2026_20260122/plan information  20260131.txt",
        "|",
        "utf-8",
    ),
    (
        "formulary_drugs",
        "Monthly Prescription Drug Plan Formulary and Pharmacy Network Information"
        "/2026_20260122/basic drugs formulary file  20260131.txt",
        "|",
        "utf-8",
    ),
    (
        "beneficiary_cost",
        "Monthly Prescription Drug Plan Formulary and Pharmacy Network Information"
        "/2026_20260122/beneficiary cost file  20260131.txt",
        "|",
        "utf-8",
    ),
]

PBP_FILES = [
    ("pbp_section_a",         "pbp-benefits-2026/pbp_Section_A.txt"),
    ("pbp_section_d",         "pbp-benefits-2026/pbp_Section_D.txt"),
    ("pbp_b7_health_prof",    "pbp-benefits-2026/pbp_b7_health_prof.txt"),
    ("pbp_b4_emerg_urgent",   "pbp-benefits-2026/pbp_b4_emerg_urgent.txt"),
    ("pbp_b16_dental",        "pbp-benefits-2026/pbp_b16_dental.txt"),
    ("pbp_b13_other_services","pbp-benefits-2026/pbp_b13_other_services.txt"),
    ("pbp_b13i_ssbci",        "pbp-benefits-2026/pbp_b13i_b19b_services_vbid_ssbci.txt"),
]


def sanitize_col(name: str) -> str:
    """Make column name safe for SQLite."""
    return name.strip().lower().replace(" ", "_").replace("-", "_").replace(".", "_")


def detect_encoding(filepath: str) -> str:
    """Detect if file is UTF-16 (BOM) or UTF-8."""
    with open(filepath, "rb") as f:
        bom = f.read(2)
    if bom in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    return "utf-8"


def load_file(db: sqlite3.Connection, table: str, filepath: str,
              delimiter: str, encoding: str = None):
    """
    Generic loader: reads header row, creates table, bulk inserts all rows.
    """
    if not os.path.isfile(filepath):
        log.warning(f"SKIP {table}: file not found at {filepath}")
        return 0

    # Auto-detect encoding if not specified
    if encoding is None:
        encoding = detect_encoding(filepath)

    log.info(f"Loading {table} from {os.path.basename(filepath)} ({encoding}, delim='{delimiter}')")

    with open(filepath, "r", encoding=encoding, errors="replace") as f:
        reader = csv.reader(f, delimiter=delimiter)
        raw_headers = next(reader)
        headers = [sanitize_col(h) for h in raw_headers]

        # Deduplicate column names (some PBP files have dupes)
        seen = {}
        deduped = []
        for h in headers:
            if h in seen:
                seen[h] += 1
                deduped.append(f"{h}_{seen[h]}")
            else:
                seen[h] = 1
                deduped.append(h)
        headers = deduped

        if not headers:
            log.warning(f"SKIP {table}: no headers found")
            return 0

        # Drop existing table
        db.execute(f"DROP TABLE IF EXISTS {table}")

        # Create table — all TEXT columns (we cast at query time)
        col_defs = ", ".join(f'"{h}" TEXT' for h in headers)
        db.execute(f"CREATE TABLE {table} ({col_defs})")

        # Prepare insert
        placeholders = ", ".join("?" for _ in headers)
        insert_sql = f"INSERT INTO {table} VALUES ({placeholders})"

        # Bulk insert in batches
        batch = []
        count = 0
        batch_size = 10000

        for row in reader:
            # Pad or trim row to match header count
            if len(row) < len(headers):
                row.extend([""] * (len(headers) - len(row)))
            elif len(row) > len(headers):
                row = row[:len(headers)]

            batch.append(row)
            count += 1

            if len(batch) >= batch_size:
                db.executemany(insert_sql, batch)
                batch = []
                if count % 100000 == 0:
                    log.info(f"  {table}: {count:,} rows...")

        if batch:
            db.executemany(insert_sql, batch)

        db.commit()

    log.info(f"  {table}: {count:,} rows loaded")
    return count


def create_indexes(db: sqlite3.Connection):
    """Create indexes for fast lookups."""
    indexes = [
        # Formulary PUF
        ("idx_pf_contract_plan", "plan_formulary", "contract_id, plan_id"),
        ("idx_pf_formulary",     "plan_formulary", "formulary_id"),
        ("idx_fd_formulary_rxcui","formulary_drugs","formulary_id, rxcui"),
        ("idx_fd_rxcui",         "formulary_drugs", "rxcui"),
        ("idx_fd_ndc",           "formulary_drugs", "ndc"),
        ("idx_bc_contract_plan", "beneficiary_cost","contract_id, plan_id, tier"),

        # PBP Benefits
        ("idx_sa_plan",  "pbp_section_a",       "pbp_a_hnumber, pbp_a_plan_identifier, segment_id"),
        ("idx_sd_plan",  "pbp_section_d",       "pbp_a_hnumber, pbp_a_plan_identifier, segment_id"),
        ("idx_b7_plan",  "pbp_b7_health_prof",  "pbp_a_hnumber, pbp_a_plan_identifier, segment_id"),
        ("idx_b4_plan",  "pbp_b4_emerg_urgent", "pbp_a_hnumber, pbp_a_plan_identifier, segment_id"),
        ("idx_b16_plan", "pbp_b16_dental",      "pbp_a_hnumber, pbp_a_plan_identifier, segment_id"),
        ("idx_b13_plan", "pbp_b13_other_services","pbp_a_hnumber, pbp_a_plan_identifier, segment_id"),
        ("idx_b13i_plan","pbp_b13i_ssbci",      "pbp_a_hnumber, pbp_a_plan_identifier, segment_id"),
    ]

    for idx_name, table, cols in indexes:
        try:
            db.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({cols})")
            log.info(f"  Index: {idx_name}")
        except Exception as e:
            log.warning(f"  Index {idx_name} skipped (table may not exist): {e}")

    db.commit()


def run_import(cms_dir: str, db_path: str):
    """Run the full import pipeline."""
    start = time.time()

    log.info(f"CMS Import Pipeline")
    log.info(f"  Source: {cms_dir}")
    log.info(f"  Database: {db_path}")
    log.info("")

    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA cache_size=-64000")  # 64MB cache

    total_rows = 0

    # Load Formulary PUF files (pipe-delimited)
    log.info("── Formulary PUF Files ──")
    for table, rel_path, delim, enc in PUF_FILES:
        filepath = os.path.join(cms_dir, rel_path)
        total_rows += load_file(db, table, filepath, delim, enc)

    # Load PBP Benefits files (tab-delimited, auto-detect encoding)
    log.info("")
    log.info("── PBP Benefits Files ──")
    for table, rel_path in PBP_FILES:
        filepath = os.path.join(cms_dir, rel_path)
        total_rows += load_file(db, table, filepath, "\t")

    # Create indexes
    log.info("")
    log.info("── Creating Indexes ──")
    create_indexes(db)

    # Summary
    elapsed = time.time() - start
    db_size = os.path.getsize(db_path) / (1024 * 1024)

    log.info("")
    log.info(f"✓ Import complete")
    log.info(f"  Total rows: {total_rows:,}")
    log.info(f"  Database size: {db_size:.1f} MB")
    log.info(f"  Time: {elapsed:.1f}s")

    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CMS Data Import Pipeline")
    parser.add_argument("--cms-dir", default="pdfs/CMS",
                        help="Path to CMS data directory (default: pdfs/CMS)")
    parser.add_argument("--db", default="cms_benefits.db",
                        help="Output SQLite database path (default: cms_benefits.db)")
    args = parser.parse_args()

    run_import(args.cms_dir, args.db)