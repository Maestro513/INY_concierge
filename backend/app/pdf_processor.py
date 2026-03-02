"""
Extract text from SOB PDFs and save as section-aware chunked JSON files.

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

import json
import os
import re

import fitz  # PyMuPDF

from .config import EXTRACTED_DIR, PDFS_DIR


# --- Section header patterns found in SOB PDFs across all carriers ---
# These match the major section headings that appear in Medicare SOB documents.
# Order matters: more specific patterns first.

SECTION_HEADERS = re.compile(
    r'^[ \t]*('
    # Plan overview / highlights
    r'(?:PLAN\s+HIGHLIGHTS|Plan\s+Highlights|PRE[\-\u2011]ENROLLMENT\s+CHECKLIST|'
    r'THINGS\s+TO\s+KNOW|Things\s+to\s+Know|PLAN\s+COSTS|Plan\s+Costs|'
    r'MONTHLY\s+PREMIUM|Monthly\s+Premium|PLAN\s+OVERVIEW|Plan\s+Overview|'
    r'ABOUT\s+THIS\s+PLAN|About\s+This\s+Plan|SUMMARY\s+OF\s+BENEFITS)'
    r'|'
    # Doctor visits / primary care
    r'(?:DOCTOR\s+VISITS|Doctor\s+Visits|PRIMARY\s+CARE|Primary\s+Care|'
    r'OFFICE\s+VISITS|Office\s+Visits|PHYSICIAN\s+SERVICES|Physician\s+Services)'
    r'|'
    # Specialist
    r'(?:SPECIALIST|Specialist)\s+(?:VISITS|Visits|SERVICES|Services)'
    r'|'
    # Preventive care
    r'(?:PREVENTIVE\s+CARE|Preventive\s+Care|PREVENTIVE\s+SERVICES|Preventive\s+Services)'
    r'|'
    # Emergency / urgent care
    r'(?:EMERGENCY\s+(?:CARE|ROOM|SERVICES)|Emergency\s+(?:Care|Room|Services))'
    r'|'
    r'(?:URGENTLY\s+NEEDED\s+CARE|Urgently\s+Needed\s+Care|URGENT\s+CARE|Urgent\s+Care)'
    r'|'
    # Inpatient hospital
    r'(?:INPATIENT\s+HOSPITAL\s+(?:COVERAGE|CARE|SERVICES)|'
    r'Inpatient\s+Hospital\s+(?:Coverage|Care|Services)|'
    r'INPATIENT\s+HOSPITAL|Inpatient\s+Hospital)'
    r'|'
    # Outpatient hospital / surgery
    r'(?:OUTPATIENT\s+HOSPITAL\s+(?:COVERAGE|CARE|SERVICES)|'
    r'Outpatient\s+Hospital\s+(?:Coverage|Care|Services)|'
    r'OUTPATIENT\s+HOSPITAL|Outpatient\s+Hospital)'
    r'|'
    r'(?:AMBULATORY\s+SURG(?:ERY|ICAL)\s+CENTER|Ambulatory\s+Surg(?:ery|ical)\s+Center)'
    r'|'
    # Skilled nursing
    r'(?:SKILLED\s+NURSING\s+FACILITY|Skilled\s+Nursing\s+Facility|SNF\s+CARE|SNF\s+Care)'
    r'|'
    # Mental health
    r'(?:MENTAL\s+HEALTH\s+(?:SERVICES|CARE)|Mental\s+Health\s+(?:Services|Care)|'
    r'BEHAVIORAL\s+HEALTH|Behavioral\s+Health|'
    r'SUBSTANCE\s+(?:ABUSE|USE)|Substance\s+(?:Abuse|Use))'
    r'|'
    # Prescription drugs
    r'(?:PRESCRIPTION\s+DRUG\s+(?:BENEFITS|COVERAGE)|Prescription\s+Drug\s+(?:Benefits|Coverage)|'
    r'PART\s+D\s+(?:PRESCRIPTION|DRUG)|Part\s+D\s+(?:Prescription|Drug)|'
    r'DRUG\s+BENEFITS|Drug\s+Benefits|PHARMACY|Pharmacy)'
    r'|'
    # Dental
    r'(?:DENTAL\s+(?:SERVICES|BENEFITS|COVERAGE)|Dental\s+(?:Services|Benefits|Coverage))'
    r'|'
    # Vision
    r'(?:VISION\s+(?:SERVICES|BENEFITS|COVERAGE)|Vision\s+(?:Services|Benefits|Coverage))'
    r'|'
    # Hearing
    r'(?:HEARING\s+(?:SERVICES|BENEFITS|COVERAGE)|Hearing\s+(?:Services|Benefits|Coverage))'
    r'|'
    # Lab / diagnostic
    r'(?:LAB\s+SERVICES|Lab\s+Services|DIAGNOSTIC\s+(?:SERVICES|TESTS)|'
    r'Diagnostic\s+(?:Services|Tests))'
    r'|'
    # Rehabilitation / therapy
    r'(?:REHABILITATION\s+SERVICES|Rehabilitation\s+Services|'
    r'PHYSICAL\s+THERAPY|Physical\s+Therapy|'
    r'OCCUPATIONAL\s+THERAPY|Occupational\s+Therapy)'
    r'|'
    # Home health / hospice
    r'(?:HOME\s+HEALTH\s+(?:CARE|SERVICES)|Home\s+Health\s+(?:Care|Services))'
    r'|'
    r'(?:HOSPICE|Hospice)'
    r'|'
    # Ambulance
    r'(?:AMBULANCE\s+(?:SERVICES)?|Ambulance\s+(?:Services)?)'
    r'|'
    # DME
    r'(?:DURABLE\s+MEDICAL\s+EQUIPMENT|Durable\s+Medical\s+Equipment|'
    r'MEDICAL\s+EQUIPMENT|Medical\s+Equipment|DME)'
    r'|'
    # Supplemental benefits
    r'(?:ADDITIONAL\s+BENEFITS|Additional\s+Benefits|'
    r'SUPPLEMENTAL\s+BENEFITS|Supplemental\s+Benefits|'
    r'EXTRA\s+BENEFITS|Extra\s+Benefits|'
    r'MORE\s+BENEFITS|More\s+Benefits|'
    r'OTHER\s+COVERED\s+(?:BENEFITS|SERVICES)|Other\s+Covered\s+(?:Benefits|Services))'
    r'|'
    # Fitness / wellness
    r'(?:FITNESS\s+(?:BENEFIT|PROGRAM)|Fitness\s+(?:Benefit|Program)|'
    r'SILVER\s*&?\s*FIT|SilverSneakers)'
    r'|'
    # OTC / flex card
    r'(?:OVER[\-\u2011]THE[\-\u2011]COUNTER|Over[\-\u2011]the[\-\u2011]Counter|OTC\s+(?:ALLOWANCE|BENEFIT))'
    r'|'
    # Transportation
    r'(?:TRANSPORTATION|Transportation)'
    r'|'
    # Telehealth
    r'(?:TELEHEALTH|Telehealth|VIRTUAL\s+VISITS|Virtual\s+Visits)'
    r'|'
    # Chiropractic / acupuncture / podiatry
    r'(?:CHIROPRACTIC|Chiropractic|ACUPUNCTURE|Acupuncture|'
    r'PODIATRY|Podiatry|FOOT\s+CARE|Foot\s+Care)'
    r'|'
    # Resources / disclaimers (end sections)
    r'(?:RESOURCES|Resources|IMPORTANT\s+NUMBERS|Important\s+Numbers|'
    r'HOW\s+TO\s+REACH\s+US|How\s+to\s+Reach\s+Us|'
    r'CUSTOMER\s+SERVICE|Customer\s+Service)'
    r')',
    re.MULTILINE
)


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


def _normalize_section_label(raw_label: str) -> str:
    """Clean up a matched section header into a readable label."""
    label = raw_label.strip()
    # Title-case it consistently
    label = " ".join(w.capitalize() if w.lower() not in ("of", "the", "and", "to", "in") else w.lower()
                     for w in label.split())
    # Collapse extra whitespace
    label = re.sub(r'\s+', ' ', label)
    return label


def chunk_by_sections(text: str, max_section_size: int = 3000, overlap: int = 200) -> list[dict]:
    """
    Split SOB text into chunks at section boundaries.

    Each chunk is a dict: {"section": "Section Name", "text": "..."}
    If a section exceeds max_section_size, it's sub-split with overlap.
    Tiny sections (<100 chars) are merged with the next section.
    """
    # Find all section header positions
    matches = list(SECTION_HEADERS.finditer(text))

    if not matches:
        # No sections detected — fall back to character-based chunking
        raw_chunks = _chunk_text_raw(text)
        return [{"section": "General", "text": c} for c in raw_chunks]

    sections = []

    # Text before the first section header
    if matches[0].start() > 100:
        sections.append({
            "section": "Plan Overview",
            "text": text[:matches[0].start()].strip(),
        })

    # Each section: from this header to the next header
    for i, match in enumerate(matches):
        label = _normalize_section_label(match.group(1))
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()

        if section_text:
            sections.append({"section": label, "text": section_text})

    # Merge tiny sections with the next one
    merged = []
    i = 0
    while i < len(sections):
        current = sections[i]
        while len(current["text"]) < 100 and i + 1 < len(sections):
            i += 1
            current["text"] += "\n\n" + sections[i]["text"]
        merged.append(current)
        i += 1

    # Sub-split oversized sections
    result = []
    for section in merged:
        if len(section["text"]) <= max_section_size:
            result.append(section)
        else:
            sub_chunks = _chunk_text_raw(section["text"], chunk_size=max_section_size, overlap=overlap)
            for j, chunk in enumerate(sub_chunks):
                label = section["section"] if j == 0 else f"{section['section']} (cont.)"
                result.append({"section": label, "text": chunk})

    return [s for s in result if len(s["text"]) > 50]


def _chunk_text_raw(text: str, chunk_size: int = 1500, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks (fallback for non-section text)."""
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


# Keep old function name for backward compat
chunk_text = _chunk_text_raw


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
    sections = chunk_by_sections(full_text)

    section_labels = [s["section"] for s in sections]
    print(f"     {len(full_text):,} chars -> {len(sections)} sections: {', '.join(section_labels[:6])}{'...' if len(section_labels) > 6 else ''}")

    results = []
    for plan_id in plan_ids:
        results.append({
            "plan_id": plan_id,
            "carrier": carrier,
            "source_file": filename,
            "full_text_length": len(full_text),
            "num_chunks": len(sections),
            "chunks": sections,
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
    print("  InsuranceNYou SOB PDF Processor")
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
