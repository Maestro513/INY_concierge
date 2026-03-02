"""
Batch extraction: run Claude on all extracted SOB JSONs to produce structured benefits.

For each extracted/{plan_id}.json, sends the full SOB text to Claude with
the SOB_EXTRACTION_PROMPT and saves the structured output to
extracted/{plan_id}_benefits.json.

Skips plans that already have a _benefits.json (incremental).
Runs 5 parallel workers for speed.

Usage:
  cd backend
  python -m app.extract_benefits            # process all (5 workers)
  python -m app.extract_benefits --force     # re-extract even if _benefits.json exists
  python -m app.extract_benefits --workers 10  # use 10 parallel workers
  python -m app.extract_benefits H1234-567   # process a single plan
"""

import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from .config import ANTHROPIC_API_KEY, EXTRACTED_DIR
from .main import SOB_EXTRACTION_PROMPT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Thread-safe counters
_lock = threading.Lock()
_stats = {"processed": 0, "errors": 0, "repaired": 0}


def _repair_json(raw: str) -> dict | None:
    """Try to repair truncated JSON from Claude (unterminated strings, missing brackets)."""
    text = raw.strip()

    # Remove trailing comma if present
    text = re.sub(r",\s*$", "", text)

    # Close any unterminated strings — find odd number of unescaped quotes
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and in_string:
            i += 2  # skip escaped char
            continue
        if ch == '"':
            in_string = not in_string
        i += 1

    if in_string:
        # We're inside an unterminated string — close it
        text += '"'

    # Count brackets and close any open ones
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")

    # Remove trailing comma before closing
    text = re.sub(r",\s*$", "", text)

    # Close arrays then objects
    text += "]" * max(0, open_brackets)
    text += "}" * max(0, open_braces)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


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
            max_tokens=16384,
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
        log.warning(f"  JSON parse failed for {plan_id}: {e}")
        log.warning("  Attempting repair...")
        parsed = _repair_json(raw)
        if parsed is None:
            log.error(f"  Repair failed for {plan_id}")
            log.error(f"  Raw (first 300 chars): {raw[:300]}")
            return None
        log.info(f"  Repair succeeded for {plan_id}")
        with _lock:
            _stats["repaired"] += 1

    return parsed


def _process_one(plan_id: str, filename: str, total: int, idx: int) -> None:
    """Process a single plan (called from thread pool)."""
    benefits_path = os.path.join(EXTRACTED_DIR, f"{plan_id}_benefits.json")

    # Load the extracted chunks
    source_path = os.path.join(EXTRACTED_DIR, filename)
    with open(source_path, "r") as f:
        data = json.load(f)

    full_text = _chunks_to_full_text(data)
    text_len = len(full_text)

    log.info(f"  [{idx}/{total}] {plan_id} ({text_len:,} chars) ...")

    # Extract via Claude
    parsed = extract_benefits_for_plan(plan_id, full_text)

    if parsed is None:
        with _lock:
            _stats["errors"] += 1
        return

    # Save structured benefits
    with open(benefits_path, "w") as f:
        json.dump(parsed, f, indent=2)

    medical_count = len(parsed.get("medical", []))
    drug_count = len(parsed.get("drugs", []))
    supp_count = len(parsed.get("supplemental", []))

    with _lock:
        _stats["processed"] += 1
        done = _stats["processed"] + _stats["errors"]

    log.info(
        f"    -> {plan_id}_benefits.json "
        f"({medical_count} medical, {drug_count} drug, {supp_count} supp) "
        f"[{done}/{total} done]"
    )


def run(plan_filter: str | None = None, force: bool = False, workers: int = 5):
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

    # Build work list (skip already extracted unless --force)
    work = []
    skipped = 0
    for filename in plan_files:
        plan_id = filename.replace(".json", "")
        benefits_path = os.path.join(EXTRACTED_DIR, f"{plan_id}_benefits.json")
        if os.path.exists(benefits_path) and not force:
            skipped += 1
            continue
        work.append((plan_id, filename))

    total = len(work)

    log.info(f"\n{'='*60}")
    log.info("  SOB Benefits Extraction (Claude API)")
    log.info(f"  {len(plan_files)} total plans, {skipped} already done, {total} to process")
    log.info(f"  Workers: {workers} parallel")
    log.info(f"  Force re-extract: {force}")
    log.info(f"{'='*60}\n")

    if total == 0:
        log.info("  Nothing to do!")
        return

    # Reset stats
    _stats["processed"] = 0
    _stats["errors"] = 0
    _stats["repaired"] = 0

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_process_one, plan_id, filename, total, i + 1): plan_id
            for i, (plan_id, filename) in enumerate(work)
        }
        for future in as_completed(futures):
            plan_id = futures[future]
            try:
                future.result()
            except Exception as e:
                log.error(f"  Unexpected error for {plan_id}: {e}")
                with _lock:
                    _stats["errors"] += 1

    elapsed = time.time() - start_time
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)

    log.info(f"\n{'='*60}")
    log.info(f"  Done in {mins}m {secs}s")
    log.info(f"  Extracted: {_stats['processed']}")
    log.info(f"  Repaired:  {_stats['repaired']}")
    log.info(f"  Errors:    {_stats['errors']}")
    log.info(f"  Skipped:   {skipped}")
    log.info(f"{'='*60}\n")


if __name__ == "__main__":
    force = "--force" in sys.argv
    # Parse --workers N
    w = 5
    if "--workers" in sys.argv:
        wi = sys.argv.index("--workers")
        if wi + 1 < len(sys.argv):
            w = int(sys.argv[wi + 1])
    args = [a for a in sys.argv[1:] if not a.startswith("--") and not a.isdigit()]
    plan_filter = args[0] if args else None
    run(plan_filter=plan_filter, force=force, workers=w)
