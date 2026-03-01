"""
Sync missing SOB PDFs from medicareadvantage.com.

Workflow:
  1. Fetch the sitemap to discover all plan URLs
  2. Scan local pdfs/ and extracted/ to know what we already have
  3. Optionally query the CMS SQLite DB for existing plan IDs
  4. Visit each missing plan's page, find the SOB PDF link, download it

Usage:
  pip install requests beautifulsoup4 lxml
  python scripts/sync_missing_sobs.py
  python scripts/sync_missing_sobs.py --dry-run          # just show what's missing
  python scripts/sync_missing_sobs.py --carrier humana    # filter by carrier
  python scripts/sync_missing_sobs.py --state NY          # filter by state
  python scripts/sync_missing_sobs.py --limit 10          # download at most 10
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

# ── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent / "backend"
PDFS_DIR = Path(os.getenv("PDFS_DIR", BACKEND_DIR / "pdfs"))
EXTRACTED_DIR = Path(os.getenv("EXTRACTED_DIR", BACKEND_DIR / "extracted"))
CMS_DB_PATH = BACKEND_DIR / "cms_benefits.db"
OUTPUT_DIR = PDFS_DIR / "sitemap_downloads"

SITEMAP_URL = "https://www.medicareadvantage.com/plans-sitemap.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Step 1: Parse sitemap ────────────────────────────────────────────────────


def fetch_sitemap(url: str = SITEMAP_URL) -> list[dict]:
    """Fetch sitemap XML and extract plan URLs with metadata."""
    print(f"\n[1/4] Fetching sitemap: {url}")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    root = ElementTree.fromstring(resp.content)

    # Handle XML namespaces (sitemaps use xmlns)
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    plans = []
    for url_elem in root.findall(f"{ns}url"):
        loc = url_elem.findtext(f"{ns}loc", "")
        if not loc:
            continue

        # Extract plan ID from URL path
        # Patterns: /plans/H1234-567-000  or  /enrollment/H1234-567
        match = re.search(r"/([HR]\d{4}-\d{3}(?:-\d{3})?)", loc)
        if not match:
            continue

        full_id = match.group(1)
        # Normalize to two-segment for matching: H1234-567
        parts = full_id.split("-")
        plan_id = f"{parts[0]}-{parts[1]}"

        # Try to extract state/carrier from URL path
        state = ""
        state_match = re.search(r"/([a-z]{2})/", loc)
        if state_match:
            state = state_match.group(1).upper()

        plans.append({
            "url": loc,
            "plan_id": plan_id,
            "full_id": full_id,
            "state": state,
        })

    # Deduplicate by plan_id (keep first URL)
    seen = set()
    unique = []
    for p in plans:
        if p["plan_id"] not in seen:
            seen.add(p["plan_id"])
            unique.append(p)

    print(f"  Found {len(unique)} unique plans in sitemap")
    return unique


# ── Step 2: Scan what we already have ────────────────────────────────────────


def get_existing_plan_ids() -> set[str]:
    """Collect plan IDs from existing PDFs, extracted JSONs, and CMS DB."""
    existing = set()

    # From PDF filenames in pdfs/ directory
    if PDFS_DIR.is_dir():
        pdf_count = 0
        for pdf in PDFS_DIR.rglob("*.pdf"):
            ids = _extract_plan_ids_from_filename(pdf.name)
            for pid in ids:
                existing.add(pid)
                pdf_count += 1
        print(f"  PDFs on disk: {pdf_count} files -> {len(existing)} plan IDs")

    # From extracted JSON files
    json_count = 0
    if EXTRACTED_DIR.is_dir():
        for jf in EXTRACTED_DIR.glob("*.json"):
            plan_id = jf.stem  # filename without extension
            if re.match(r"[HR]\d{4}-\d{3}", plan_id):
                existing.add(plan_id)
                json_count += 1
    print(f"  Extracted JSONs: {json_count} files")

    # From CMS database
    if CMS_DB_PATH.is_file():
        try:
            conn = sqlite3.connect(str(CMS_DB_PATH))
            rows = conn.execute(
                "SELECT DISTINCT contract_id, plan_id FROM plan_formulary"
            ).fetchall()
            db_count = 0
            for cid, pid in rows:
                existing.add(f"{cid}-{pid}")
                db_count += 1
            conn.close()
            print(f"  CMS database: {db_count} plan IDs")
        except Exception as e:
            print(f"  CMS database: skipped ({e})")

    return existing


def _extract_plan_ids_from_filename(filename: str) -> list[str]:
    """Extract plan IDs from PDF filename (matches pdf_processor.py logic)."""
    name = os.path.splitext(filename)[0]

    # Humana compact: H0028007000SB26 -> H0028-007
    compact = re.match(r"^(H\d{4})(\d{3})\d{3}SB", name, re.IGNORECASE)
    if compact:
        return [f"{compact.group(1)}-{compact.group(2)}"]

    # Three-segment: H1234-567-890
    three_seg = re.findall(r"[HR]\d{4}-\d{3}-\d{3}", name)
    if three_seg:
        return [f"{m.rsplit('-', 1)[0]}" for m in three_seg]

    # Two-segment: H7617-038
    two_seg = re.findall(r"[HR]\d{4}-\d{3}", name)
    if two_seg:
        return list(dict.fromkeys(two_seg))

    # Aetna underscore: H1610_001
    y_match = re.findall(r"(H\d{4})_(\d{3})", name)
    if y_match:
        return [f"{h}-{seg}" for h, seg in dict.fromkeys(y_match)]

    return []


# ── Step 3: Find and download SOB PDFs from plan pages ───────────────────────


def find_sob_link(plan_url: str) -> str | None:
    """Visit a plan page and find the Summary of Benefits PDF link."""
    try:
        resp = requests.get(plan_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    SKIP: couldn't load page ({e})")
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # Look for links containing "summary of benefits" or "sob"
    for a in soup.find_all("a", href=True):
        text = (a.get_text() or "").lower()
        href = a["href"].lower()

        if any(
            kw in text or kw in href
            for kw in ["summary of benefits", "sob", "summary-of-benefits"]
        ):
            link = a["href"]
            # Make absolute
            if link.startswith("/"):
                link = f"https://www.medicareadvantage.com{link}"
            if link.endswith(".pdf") or "pdf" in link.lower():
                return link

    return None


def download_pdf(url: str, dest: Path) -> bool:
    """Download a PDF file, following redirects."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()

        # Verify it's actually a PDF
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type and not url.endswith(".pdf"):
            print(f"    SKIP: not a PDF (Content-Type: {content_type})")
            return False

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        tmp.rename(dest)
        size_kb = dest.stat().st_size / 1024
        print(f"    Downloaded: {dest.name} ({size_kb:.0f} KB)")
        return True

    except Exception as e:
        print(f"    FAILED: {e}")
        return False


# ── Main pipeline ────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Download missing SOB PDFs from medicareadvantage.com sitemap"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Only show what's missing, don't download")
    parser.add_argument("--carrier", type=str, default="",
                        help="Filter sitemap URLs by carrier name in path")
    parser.add_argument("--state", type=str, default="",
                        help="Filter by state code (e.g. NY, FL)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max number of PDFs to download (0 = unlimited)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds between requests (be respectful)")
    parser.add_argument("--output-dir", type=str, default="",
                        help="Override output directory for downloaded PDFs")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR

    # Step 1: Get all plans from sitemap
    sitemap_plans = fetch_sitemap()

    # Apply filters
    if args.carrier:
        carrier = args.carrier.lower()
        sitemap_plans = [p for p in sitemap_plans if carrier in p["url"].lower()]
        print(f"  After carrier filter '{args.carrier}': {len(sitemap_plans)} plans")

    if args.state:
        state = args.state.upper()
        sitemap_plans = [p for p in sitemap_plans if p["state"] == state]
        print(f"  After state filter '{args.state}': {len(sitemap_plans)} plans")

    if not sitemap_plans:
        print("\nNo plans found in sitemap matching filters.")
        return

    # Step 2: Find what we already have
    print(f"\n[2/4] Scanning existing plan data...")
    existing_ids = get_existing_plan_ids()
    print(f"  Total existing plan IDs: {len(existing_ids)}")

    # Step 3: Compute the diff
    print(f"\n[3/4] Computing missing plans...")
    missing = [p for p in sitemap_plans if p["plan_id"] not in existing_ids]
    already_have = len(sitemap_plans) - len(missing)

    print(f"  Sitemap plans:  {len(sitemap_plans)}")
    print(f"  Already have:   {already_have}")
    print(f"  Missing:        {len(missing)}")

    if not missing:
        print("\nAll plans accounted for! Nothing to download.")
        return

    if args.dry_run:
        print(f"\n[DRY RUN] Missing plan IDs:")
        for p in missing[:50]:
            print(f"  {p['plan_id']}  {p['url']}")
        if len(missing) > 50:
            print(f"  ... and {len(missing) - 50} more")

        # Save full list to a JSON
        out_file = output_dir / "_missing_plans.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w") as f:
            json.dump(missing, f, indent=2)
        print(f"\n  Full list saved to: {out_file}")
        return

    # Step 4: Download missing SOBs
    limit = args.limit if args.limit > 0 else len(missing)
    to_download = missing[:limit]

    print(f"\n[4/4] Downloading SOBs for {len(to_download)} missing plans...")
    print(f"  Output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {"downloaded": 0, "no_sob_link": 0, "failed": 0, "details": []}

    for i, plan in enumerate(to_download, 1):
        plan_id = plan["plan_id"]
        url = plan["url"]
        print(f"\n  [{i}/{len(to_download)}] {plan_id}")
        print(f"    Page: {url}")

        # Find SOB link on the plan page
        sob_url = find_sob_link(url)
        if not sob_url:
            print(f"    No SOB PDF link found on page")
            results["no_sob_link"] += 1
            results["details"].append({"plan_id": plan_id, "status": "no_sob_link"})
            time.sleep(args.delay)
            continue

        print(f"    SOB: {sob_url}")

        # Download the PDF
        pdf_name = f"{plan_id}_SOB.pdf"
        dest = output_dir / pdf_name

        if dest.is_file():
            print(f"    Already downloaded: {pdf_name}")
            results["downloaded"] += 1
            results["details"].append({"plan_id": plan_id, "status": "already_exists"})
        elif download_pdf(sob_url, dest):
            results["downloaded"] += 1
            results["details"].append({
                "plan_id": plan_id, "status": "downloaded",
                "sob_url": sob_url, "file": str(dest),
            })
        else:
            results["failed"] += 1
            results["details"].append({
                "plan_id": plan_id, "status": "failed", "sob_url": sob_url,
            })

        time.sleep(args.delay)

    # Summary
    print(f"\n{'='*50}")
    print(f"  Download Summary")
    print(f"  Downloaded:    {results['downloaded']}")
    print(f"  No SOB link:   {results['no_sob_link']}")
    print(f"  Failed:        {results['failed']}")
    print(f"{'='*50}")

    # Save summary
    summary_path = output_dir / "_download_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Summary saved to: {summary_path}")


if __name__ == "__main__":
    main()
