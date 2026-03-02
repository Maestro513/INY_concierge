"""
Rename SOB PDFs to human-readable names based on extracted JSON content.

Output format: "Plan Name (Plan Type) H1234-567.pdf"
Example:      "Humana Gold Plus (HMO) H0028-014.pdf"

All renamed files stay in their current location (same folder).

Usage:
  python rename_pdfs.py              # dry run (shows what would change)
  python rename_pdfs.py --apply      # actually rename files
"""

import json
import os
import re
import sys

from app.config import EXTRACTED_DIR, PDFS_DIR


def _extract_plan_name(plan_id: str, extracted_dir: str) -> str | None:
    """Extract the human-readable plan name from the first chunk of extracted JSON."""
    path = os.path.join(extracted_dir, f"{plan_id}.json")
    if not os.path.exists(path):
        return None

    with open(path) as f:
        data = json.load(f)

    chunks = data.get("chunks", [])
    if not chunks:
        return None

    first_text = chunks[0]["text"] if isinstance(chunks[0], dict) else str(chunks[0])

    # Normalize the plan ID for matching (H0028-007 -> H0028007)
    pid_compact = plan_id.replace("-", "")

    lines = first_text.split("\n")

    # Strategy 1: Find a line with the H-number AND a plan type keyword
    plan_type_keywords = ["HMO", "PPO", "PFFS", "SNP", "POS", "DSNP", "MSA", "LPPO"]
    carrier_names = ["HUMANA", "AETNA", "UHC", "UNITED", "DEVOTED", "WELLCARE",
                     "ANTHEM", "BCBS", "BLUE CROSS", "MOLINA", "KAISER", "ZING",
                     "HEALTHSPRING", "WELLPOINT", "CENTRAL", "PASSPORT", "EXPERIENCE"]

    for i, line in enumerate(lines):
        line = line.strip()
        line_compact = line.replace("-", "").replace(" ", "").replace("_", "")
        if pid_compact.upper() in line_compact.upper() or plan_id in line:
            if any(kw in line.upper() for kw in plan_type_keywords):
                name = _clean_plan_name(line, plan_id)
                # If the name doesn't contain a carrier, check the previous line
                if not any(c in name.upper() for c in carrier_names):
                    for j in range(max(0, i - 3), i):
                        prev = lines[j].strip()
                        if prev and len(prev) > 3 and not prev.isdigit():
                            if any(c in prev.upper() for c in carrier_names) or (
                                len(prev) > 5 and "summary" not in prev.lower()
                                and "sbosb" not in prev.lower()
                                and not prev.upper().startswith("H")
                                and not prev.upper().startswith("S")
                            ):
                                name = f"{prev.strip()} {name}"
                                break
                return name

    # Strategy 2: For carriers like Devoted that put plan name on a separate line
    for i, line in enumerate(lines[:20]):
        line = line.strip()
        if any(kw in line.upper() for kw in plan_type_keywords):
            if len(line) > 10 and not line.startswith("1-") and "http" not in line.lower():
                if "member services" not in line.lower() and "call" not in line.lower():
                    return _clean_plan_name(line, plan_id)

    return None


def _clean_plan_name(raw_name: str, plan_id: str) -> str:
    """Clean up a raw plan name string into a nice filename."""
    name = raw_name.strip()

    # Remove the plan ID from the name (we'll add it at the end)
    name = name.replace(plan_id, "")
    name = name.replace(plan_id.replace("-", ""), "")

    # Remove common junk
    junk_patterns = [
        r":\s*Summary of Benefits\s*\d*",
        r"Summary of Benefits",
        r"PBP Number:?\s*\S+",
        r"^\d+\s+",
        r"\bSB\d+\b",
        r"\bSBOSB\d+\b",
        r"\b\d{3,}SB\d+\b",
        r"H\d{4,}\d{3,}",
        r"-\d{3}\b",
        r"\bPlan\b",  # trailing "Plan" word
        r"\$\d+[\.\d]*\s*Premium",  # "$0 Premium", "$0.00 Premium"
    ]
    for pat in junk_patterns:
        name = re.sub(pat, "", name, flags=re.IGNORECASE)

    # Replace underscores with spaces
    name = name.replace("_", " ")

    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()

    # Remove leading/trailing punctuation
    name = name.strip(" -,:")

    # Make sure parentheses are balanced
    open_count = name.count("(")
    close_count = name.count(")")
    if open_count > close_count:
        name += ")" * (open_count - close_count)

    return name


def _build_pdf_index(pdfs_dir: str) -> dict:
    """Build an index of plan_id -> pdf_path for fast lookup."""
    index = {}
    for root, dirs, files in os.walk(pdfs_dir):
        if "CMS" in root or "cms" in root:
            continue
        for fname in files:
            if not fname.lower().endswith(".pdf"):
                continue
            full_path = os.path.join(root, fname)
            fname_upper = fname.upper()

            # Extract all plan IDs from the filename
            # Matches: H0028-007, R6694-006, S5601-038, and variants
            h_matches = re.findall(r"[HRS]\d{4}[-_]?\d{2,3}[-_]?\d{0,3}", fname_upper)
            for h in h_matches:
                clean = h.replace("_", "").replace("-", "")
                if len(clean) >= 8:
                    # Index as H1234-567
                    short = f"{clean[:5]}-{clean[5:8]}"
                    if short not in index:
                        index[short] = full_path
                    # Also index as H1234-567-000 if there's a 3rd part
                    if len(clean) >= 11:
                        long_id = f"{clean[:5]}-{clean[5:8]}-{clean[8:11]}"
                        if long_id not in index:
                            index[long_id] = full_path

    return index


def _safe_filename(name: str) -> str:
    """Remove characters that are invalid in filenames."""
    # Replace non-breaking hyphens and other Unicode dashes with regular hyphen
    name = name.replace("\u2011", "-").replace("\u2010", "-").replace("\u2013", "-").replace("\u2014", "-")
    # Replace any other non-ASCII characters
    name = name.encode("ascii", "replace").decode("ascii").replace("?", "")
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def run(apply: bool = False):
    """Rename all PDFs based on extracted plan names."""
    extracted_files = sorted(os.listdir(EXTRACTED_DIR))
    plan_ids = [
        f.replace(".json", "")
        for f in extracted_files
        if f.endswith(".json")
        and not f.endswith("_benefits.json")
        and (f.startswith("H") or f.startswith("R") or f.startswith("S"))
    ]

    print(f"\n{'='*60}")
    print("  SOB PDF Renamer")
    print(f"  {len(plan_ids)} plans to process")
    print(f"  Mode: {'APPLY' if apply else 'DRY RUN'}")
    print(f"{'='*60}\n")

    # Build PDF index once (much faster than walking for each plan)
    print("  Building PDF index...")
    pdf_index = _build_pdf_index(PDFS_DIR)
    print(f"  Found {len(pdf_index)} PDFs indexed.\n")

    renamed = 0
    skipped = 0
    not_found = 0
    no_name = 0

    for plan_id in plan_ids:
        plan_name = _extract_plan_name(plan_id, EXTRACTED_DIR)
        if not plan_name:
            no_name += 1
            continue

        pdf_path = pdf_index.get(plan_id)
        # Try short form (H1234-567) if full form (H1234-567-000) not found
        if not pdf_path and len(plan_id.split("-")) == 3:
            short_id = "-".join(plan_id.split("-")[:2])
            pdf_path = pdf_index.get(short_id)
        if not pdf_path:
            not_found += 1
            continue

        new_filename = _safe_filename(f"{plan_name} {plan_id}.pdf")
        new_path = os.path.join(os.path.dirname(pdf_path), new_filename)

        if os.path.basename(pdf_path) == new_filename:
            skipped += 1
            continue

        old_name = os.path.basename(pdf_path)
        print(f"  {old_name}")
        print(f"    -> {new_filename}")

        if apply:
            try:
                os.rename(pdf_path, new_path)
                renamed += 1
            except OSError as e:
                print(f"    ERROR: {e}")
        else:
            renamed += 1

    print(f"\n{'='*60}")
    action = "Renamed" if apply else "Would rename"
    print(f"  {action}: {renamed}")
    print(f"  Skipped (already named): {skipped}")
    print(f"  PDF not found: {not_found}")
    print(f"  Name not extracted: {no_name}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    run(apply=apply)
