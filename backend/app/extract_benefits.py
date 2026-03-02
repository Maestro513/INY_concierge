"""
Batch extraction: run Claude on all extracted SOB JSONs to produce structured benefits.

For each extracted/{plan_id}.json, sends the full SOB text to Claude with
the SOB_EXTRACTION_PROMPT and saves the structured output to
extracted/{plan_id}_benefits.json.

Skips plans that already have a _benefits.json (incremental).
Rate-limited to ~1 request/sec to avoid API throttling.

Usage:
  cd backend
  python -m app.extract_benefits            # process all
  python -m app.extract_benefits --force     # re-extract even if _benefits.json exists
  python -m app.extract_benefits H1234-567   # process a single plan
"""

import os
import sys
import json
import time
import logging
import anthropic
from .config import ANTHROPIC_API_KEY, EXTRACTED_DIR

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# Import the extraction prompt from main.py to stay in sync
from .main import SOB_EXTRACTION_PROMPT


def _chunks_to_full_text(data: dict) -> str:
    """Join all chunks from an extracted JSON into a single context string."""
    chunks = data.get("chunks", [])
    parts = []
    for c in chunks:
        if isinstance(c, dict):
            parts.append(f"[{c['section']}]\n{c['text']}")
        else:
            parts.append(c)
    return "\n\n---\n\n".join(parts)


def extract_benefits_for_plan(plan_id: str, full_text: str) -> dict | None:
    """Send SOB text to Claude and parse the structured benefits JSON."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            system=SOB_EXTRACTION_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Plan: {plan_id}\n\nFull document text:\n\n{full_text}",
                }
            ],
        )
    except Exception as e:
        log.error(f"  API error for {plan_id}: {e}")
        return None

    raw = message.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f"  JSON parse failed for {plan_id}: {e}")
        log.error(f"  Raw (first 300 chars): {raw[:300]}")
        return None

    return parsed


def run(plan_filter: str | None = None, force: bool = False):
    """Process all extracted JSONs (or a single plan) through Claude."""
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY not set. Add it to backend/.env")
        return

    os.makedirs(EXTRACTED_DIR, exist_ok=True)

    # Find all plan JSONs (not _benefits.json files)
    all_files = sorted(os.listdir(EXTRACTED_DIR))
    plan_files = [
        f for f in all_files
        if f.endswith(".json") and not f.endswith("_benefits.json")
    ]

    if plan_filter:
        plan_files = [f for f in plan_files if plan_filter in f]

    if not plan_files:
        log.info(f"No extracted JSONs found in {EXTRACTED_DIR}")
        log.info("Run `python -m app.pdf_processor` first to extract PDFs.")
        return

    log.info(f"\n{'='*60}")
    log.info(f"  SOB Benefits Extraction (Claude API)")
    log.info(f"  {len(plan_files)} plan(s) to process")
    log.info(f"  Force re-extract: {force}")
    log.info(f"{'='*60}\n")

    processed = 0
    skipped = 0
    errors = 0

    for filename in plan_files:
        plan_id = filename.replace(".json", "")
        benefits_path = os.path.join(EXTRACTED_DIR, f"{plan_id}_benefits.json")

        # Skip if already extracted (unless --force)
        if os.path.exists(benefits_path) and not force:
            log.info(f"  SKIP {plan_id} (already extracted)")
            skipped += 1
            continue

        # Load the extracted chunks
        source_path = os.path.join(EXTRACTED_DIR, filename)
        with open(source_path, "r") as f:
            data = json.load(f)

        full_text = _chunks_to_full_text(data)
        text_len = len(full_text)

        log.info(f"  {plan_id} ({text_len:,} chars) ...")

        # Extract via Claude
        parsed = extract_benefits_for_plan(plan_id, full_text)

        if parsed is None:
            errors += 1
            continue

        # Save structured benefits
        with open(benefits_path, "w") as f:
            json.dump(parsed, f, indent=2)

        medical_count = len(parsed.get("medical", []))
        drug_count = len(parsed.get("drugs", []))
        log.info(f"    -> {plan_id}_benefits.json ({medical_count} medical, {drug_count} drug rows)")

        processed += 1

        # Rate limit: ~1 request/sec
        time.sleep(1.0)

    log.info(f"\n{'='*60}")
    log.info(f"  Done! {processed} extracted, {skipped} skipped, {errors} errors")
    log.info(f"{'='*60}\n")


if __name__ == "__main__":
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    plan_filter = args[0] if args else None
    run(plan_filter=plan_filter, force=force)
