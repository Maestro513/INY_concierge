"""
Extract text from SOB PDFs and save as chunked JSON files.

Handles all carrier filename formats:
  Humana:   H7617-038.PDF / H0028007000SB26.PDF
  Aetna:    H1610_001_DS17_SB2026_M.pdf / Y0001_H0523_022_HP01_SB2026_M.pdf
  Devoted:  2026-DEVOTED-C-SNP-003-NM-(HMO-C-SNP)-SB-H9977-003-ENG.pdf
  UHC:      2026 English SB-...H2406-129-000.pdf / ...R3444-009-000.pdf
  Zing:     2026_SOB_IL_H4624-001_EN.pdf / 2026_SOB_IN_H4624-003_H6876-004_EN.pdf

Scans subfolders (carrier/state/etc).

Usage:
  python -m app.pdf_processor
"""

import os
import re
import json
import fitz  # PyMuPDF
from .config import PDFS_DIR, EXTRACTED_DIR


def extract_plan_ids(filename: str) -> list[str]:
    """
    Extract plan ID(s) from any carrier filename format.
    Returns a list because some files (Zing) map to multiple plan IDs.
    """
    name = os.path.splitext(filename)[0]

    # --- Humana compact: H0028007000SB26 -> H0028-007 ---
    compact = re.match(r"^(H\d{4})(\d{3})\d{3}SB", name, re.IGNORECASE)
    if compact:
        return [f"{compact.group(1)}-{compact.group(2)}"]

    # --- Find all H-number or R-number patterns in filename ---
    # Three-segment: H1234-567-890 or R1234-567-890
    three_seg = re.findall(r"[HR]\d{4}-\d{3}-\d{3}", name)
    if three_seg:
        return list(dict.fromkeys(three_seg))

    # Two-segment with dash: H7617-038
    two_seg_dash = re.findall(r"[HR]\d{4}-\d{3}", name)
    if two_seg_dash:
        return list(dict.fromkeys(two_seg_dash))

    # Two-segment with underscore (Aetna): H1610_001 or Y0001_H0523_022
    y_match = re.findall(r"(H\d{4})_(\d{3})", name)
    if y_match:
        return [f"{h}-{seg}" for h, seg in dict.fromkeys(y_match)]

    # Fallback: use full filename
    print(f"  WARNING: Could not extract plan ID from: {filename}")
    return [name]


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF file."""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    doc.close()
    return text.strip()


def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks for better context retrieval."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if end < len(text):
            last_period = chunk.rfind(". ")
            last_newline = chunk.rfind("\n")
            break_at = max(last_period, last_newline)
            if break_at > chunk_size * 0.5:
                end = start + break_at + 1
                chunk = text[start:end]
        chunks.append(chunk.strip())
        start = end - overlap
    return [c for c in chunks if len(c) > 50]


def get_carrier_from_path(pdf_path: str, base_dir: str) -> str:
    """Infer carrier name from folder structure."""
    rel = os.path.relpath(pdf_path, base_dir)
    parts = rel.split(os.sep)
    if len(parts) > 1:
        return parts[0]
    return "Unknown"


def process_single_pdf(pdf_path: str, base_dir: str) -> list[dict]:
    """Process a single PDF. Returns a list (one per plan ID, usually just one)."""
    filename = os.path.basename(pdf_path)
    carrier = get_carrier_from_path(pdf_path, base_dir)
    plan_ids = extract_plan_ids(filename)

    print(f"  {filename}")
    print(f"     Carrier: {carrier}")
    print(f"     Plan ID(s): {', '.join(plan_ids)}")

    full_text = extract_text_from_pdf(pdf_path)
    chunks = chunk_text(full_text)

    print(f"     {len(full_text):,} chars -> {len(chunks)} chunks")

    results = []
    for plan_id in plan_ids:
        results.append({
            "plan_id": plan_id,
            "carrier": carrier,
            "source_file": filename,
            "full_text_length": len(full_text),
            "num_chunks": len(chunks),
            "chunks": chunks,
        })

    return results


def process_pdf_list(pdf_files: list[str]) -> dict:
    """Process a specific list of PDF file paths. Returns summary."""
    os.makedirs(EXTRACTED_DIR, exist_ok=True)

    total_plans = 0
    errors = []

    for pdf_path in sorted(pdf_files):
        if not pdf_path.lower().endswith(".pdf"):
            continue
        try:
            results = process_single_pdf(pdf_path, PDFS_DIR)
            for data in results:
                out_path = os.path.join(EXTRACTED_DIR, f"{data['plan_id']}.json")
                with open(out_path, "w") as f:
                    json.dump(data, f, indent=2)
                total_plans += 1
                print(f"     -> {data['plan_id']}.json")
            print()
        except Exception as e:
            errors.append((pdf_path, str(e)))
            print(f"     ERROR: {e}\n")

    return {"processed": total_plans, "errors": len(errors)}


def process_all_pdfs():
    """Process all PDFs in the pdfs/ directory (including subfolders)."""
    pdf_files = []
    for root, dirs, files in os.walk(PDFS_DIR):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdf_files.append(os.path.join(root, f))

    if not pdf_files:
        print(f"\nNo PDFs found in {PDFS_DIR}")
        print("Add SOB PDFs to pdfs/ (subfolders by carrier/state OK).\n")
        return

    print(f"\n{'='*60}")
    print(f"  InsuranceNYou SOB PDF Processor")
    print(f"  Found {len(pdf_files)} PDF(s)")
    print(f"{'='*60}\n")

    result = process_pdf_list(pdf_files)

    print(f"{'='*60}")
    print(f"  Done! {result['processed']} plan files created from {len(pdf_files)} PDFs")
    if result["errors"]:
        print(f"  {result['errors']} error(s)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    process_all_pdfs()