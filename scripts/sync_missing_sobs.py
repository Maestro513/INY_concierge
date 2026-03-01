"""
Sync missing SOB PDFs from medicareadvantage.com sitemap.

Workflow:
  1. Scan your local Pdfs folder to find all plan IDs you already have
  2. Fetch the sitemap to discover all available plan URLs
  3. Diff them — figure out what's missing
  4. Visit each missing plan's page, find the SOB PDF link, download it
     into the same Pdfs folder

Usage (run from your local machine):
  pip install requests beautifulsoup4 lxml
  python sync_missing_sobs.py --dry-run                    # see what's missing
  python sync_missing_sobs.py                              # download missing
  python sync_missing_sobs.py --limit 10                   # download 10 at a time
  python sync_missing_sobs.py --pdfs-dir "D:\\other\\path"  # custom folder
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

# ── Default paths (Windows) ─────────────────────────────────────────────────

DEFAULT_PDFS_DIR = r"C:\Users\tank5\OneDrive\Concierge\backend\Pdfs"

SITEMAP_URL = "https://www.medicareadvantage.com/plans-sitemap.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ── Plan ID extraction from filenames ────────────────────────────────────────


def extract_plan_ids_from_filename(filename: str) -> list[str]:
    """
    Pull H/R-number plan IDs from any carrier filename format.
    Returns normalized two-segment IDs like H1234-567.
    """
    name = os.path.splitext(filename)[0]

    # Humana compact: H0028007000SB26 -> H0028-007
    compact = re.match(r"^(H\d{4})(\d{3})\d{3}SB", name, re.IGNORECASE)
    if compact:
        return [f"{compact.group(1)}-{compact.group(2)}"]

    # Three-segment: H1234-567-890 or R1234-567-890
    three_seg = re.findall(r"[HR]\d{4}-\d{3}-\d{3}", name)
    if three_seg:
        # Normalize to two-segment
        return list(dict.fromkeys(f"{m.rsplit('-', 1)[0]}" for m in three_seg))

    # Two-segment with dash: H7617-038
    two_seg = re.findall(r"[HR]\d{4}-\d{3}", name)
    if two_seg:
        return list(dict.fromkeys(two_seg))

    # Aetna underscore: H1610_001
    y_match = re.findall(r"(H\d{4})_(\d{3})", name)
    if y_match:
        return [f"{h}-{seg}" for h, seg in dict.fromkeys(y_match)]

    return []


# ── Step 1: Scan local PDFs ─────────────────────────────────────────────────


def scan_existing_pdfs(pdfs_dir: Path) -> dict[str, Path]:
    """
    Walk the Pdfs folder (including subfolders) and build a map of
    plan_id -> folder_path for every PDF we already have.

    Returns: { "H1234-567": Path("C:/Users/.../Pdfs/Humana"), ... }
    """
    existing = {}  # plan_id -> parent folder path

    if not pdfs_dir.is_dir():
        print(f"  WARNING: Pdfs directory not found: {pdfs_dir}")
        return existing

    pdf_count = 0
    for pdf in pdfs_dir.rglob("*.pdf"):
        ids = extract_plan_ids_from_filename(pdf.name)
        for pid in ids:
            if pid not in existing:
                existing[pid] = pdf.parent
            pdf_count += 1

    print(f"  Scanned {pdf_count} PDF files")
    print(f"  Found {len(existing)} unique plan IDs on disk")

    # Show subfolder breakdown
    folders = {}
    for pid, folder in existing.items():
        rel = folder.relative_to(pdfs_dir) if folder != pdfs_dir else Path(".")
        folder_name = str(rel)
        folders[folder_name] = folders.get(folder_name, 0) + 1

    if folders:
        print(f"  Folders:")
        for folder, count in sorted(folders.items()):
            print(f"    {folder}: {count} plans")

    return existing


# ── Step 2: Fetch sitemap ────────────────────────────────────────────────────


def fetch_sitemap(url: str = SITEMAP_URL) -> list[dict]:
    """Fetch sitemap XML and extract plan URLs with metadata."""
    print(f"\n[2/4] Fetching sitemap: {url}")
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

        # Try to extract state from URL path (e.g. /ny/ or /florida/)
        state = ""
        state_match = re.search(r"/([a-z]{2})/", loc)
        if state_match:
            state = state_match.group(1).upper()

        # Try to extract carrier from URL
        carrier = ""
        for c in ["humana", "aetna", "uhc", "united", "devoted", "wellcare",
                   "cigna", "zing", "healthspring", "anthem", "blue"]:
            if c in loc.lower():
                carrier = c.capitalize()
                break

        plans.append({
            "url": loc,
            "plan_id": plan_id,
            "full_id": full_id,
            "state": state,
            "carrier": carrier,
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


# ── Step 3: Find SOB link on plan page ───────────────────────────────────────


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

        if any(kw in text or kw in href for kw in [
            "summary of benefits", "summary-of-benefits",
            "sob", "plan-document",
        ]):
            link = a["href"]
            # Make absolute
            if link.startswith("/"):
                link = f"https://www.medicareadvantage.com{link}"
            # Accept PDF links or links that look like document endpoints
            if ".pdf" in link.lower() or "document" in link.lower():
                return link

    return None


# ── Step 4: Download ─────────────────────────────────────────────────────────


def download_pdf(url: str, dest: Path) -> bool:
    """Download a PDF file, following redirects."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60, stream=True,
                            allow_redirects=True)
        resp.raise_for_status()

        # Check we actually got a PDF
        content_type = resp.headers.get("Content-Type", "")
        first_bytes = b""
        chunks = []
        for chunk in resp.iter_content(chunk_size=8192):
            chunks.append(chunk)
            if not first_bytes:
                first_bytes = chunk[:5]

        if first_bytes[:4] != b"%PDF" and "pdf" not in content_type:
            print(f"    SKIP: not a PDF (Content-Type: {content_type})")
            return False

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            for chunk in chunks:
                f.write(chunk)
        tmp.rename(dest)
        size_kb = dest.stat().st_size / 1024
        print(f"    OK: {dest.name} ({size_kb:.0f} KB)")
        return True

    except Exception as e:
        print(f"    FAILED: {e}")
        return False


# ── Decide download folder ───────────────────────────────────────────────────


def pick_download_folder(plan: dict, pdfs_dir: Path) -> Path:
    """
    Decide which subfolder to save a new PDF into.
    Uses carrier name if available, otherwise puts in root Pdfs/ folder.
    """
    carrier = plan.get("carrier", "")
    if carrier:
        return pdfs_dir / carrier
    return pdfs_dir


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Download missing SOB PDFs by cross-referencing the sitemap"
    )
    parser.add_argument("--pdfs-dir", type=str, default=DEFAULT_PDFS_DIR,
                        help=f"Path to your Pdfs folder (default: {DEFAULT_PDFS_DIR})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only show what's missing, don't download")
    parser.add_argument("--carrier", type=str, default="",
                        help="Filter sitemap by carrier name")
    parser.add_argument("--state", type=str, default="",
                        help="Filter by state code (e.g. NY, FL)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max PDFs to download (0 = all)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds between requests (default: 2)")
    args = parser.parse_args()

    pdfs_dir = Path(args.pdfs_dir)

    print("=" * 60)
    print("  SOB PDF Sync — medicareadvantage.com sitemap")
    print("=" * 60)

    # Step 1: Scan local PDFs
    print(f"\n[1/4] Scanning local PDFs: {pdfs_dir}")
    existing = scan_existing_pdfs(pdfs_dir)

    # Step 2: Fetch sitemap
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

    # Step 3: Compute diff
    print(f"\n[3/4] Computing missing plans...")
    missing = [p for p in sitemap_plans if p["plan_id"] not in existing]
    already_have = len(sitemap_plans) - len(missing)

    print(f"  Sitemap total:  {len(sitemap_plans)}")
    print(f"  Already have:   {already_have}")
    print(f"  MISSING:        {len(missing)}")

    if not missing:
        print("\nAll plans accounted for! Nothing to download.")
        return

    # Dry run — just list what's missing
    if args.dry_run:
        print(f"\n--- DRY RUN: Missing plan IDs ---")
        for p in missing[:100]:
            print(f"  {p['plan_id']:15s}  {p.get('carrier',''):12s}  {p['url']}")
        if len(missing) > 100:
            print(f"  ... and {len(missing) - 100} more")

        # Save full list
        out_file = pdfs_dir / "_missing_plans.json"
        with open(out_file, "w") as f:
            json.dump(missing, f, indent=2)
        print(f"\n  Full list saved to: {out_file}")
        return

    # Step 4: Download
    limit = args.limit if args.limit > 0 else len(missing)
    to_download = missing[:limit]

    print(f"\n[4/4] Downloading SOBs for {len(to_download)} missing plans...")

    results = {"downloaded": 0, "no_sob_link": 0, "failed": 0, "details": []}

    for i, plan in enumerate(to_download, 1):
        plan_id = plan["plan_id"]
        full_id = plan["full_id"]
        url = plan["url"]
        print(f"\n  [{i}/{len(to_download)}] {plan_id}")
        print(f"    Page: {url}")

        # Find SOB link on the plan page
        sob_url = find_sob_link(url)
        if not sob_url:
            print(f"    No SOB PDF link found")
            results["no_sob_link"] += 1
            results["details"].append({"plan_id": plan_id, "status": "no_sob_link",
                                       "url": url})
            time.sleep(args.delay)
            continue

        print(f"    SOB link: {sob_url}")

        # Pick folder and filename
        folder = pick_download_folder(plan, pdfs_dir)
        pdf_name = f"{full_id}_SOB_2026.pdf"
        dest = folder / pdf_name

        if dest.is_file():
            print(f"    Already exists: {dest}")
            results["downloaded"] += 1
            results["details"].append({"plan_id": plan_id, "status": "exists"})
        elif download_pdf(sob_url, dest):
            results["downloaded"] += 1
            results["details"].append({
                "plan_id": plan_id, "status": "downloaded",
                "file": str(dest), "sob_url": sob_url,
            })
        else:
            results["failed"] += 1
            results["details"].append({
                "plan_id": plan_id, "status": "failed", "sob_url": sob_url,
            })

        time.sleep(args.delay)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  DONE")
    print(f"  Downloaded:    {results['downloaded']}")
    print(f"  No SOB link:   {results['no_sob_link']}")
    print(f"  Failed:        {results['failed']}")
    print(f"{'=' * 60}")

    # Save summary
    summary_path = pdfs_dir / "_download_summary.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Summary: {summary_path}")


if __name__ == "__main__":
    main()
