#!/usr/bin/env bash
set -e

echo "=== InsuranceNYou Backend Startup ==="

# 1. Download PDFs from Google Drive (skips if already on disk)
python download_pdfs.py

# 2. Process PDFs into extracted JSON (skips if already done)
EXTRACTED=${EXTRACTED_DIR:-extracted}
PDF_COUNT=$(find "${PDFS_DIR:-pdfs}" -iname '*.pdf' 2>/dev/null | wc -l)
JSON_COUNT=$(find "$EXTRACTED" -iname '*.json' 2>/dev/null | wc -l)

if [ "$PDF_COUNT" -gt 0 ] && [ "$JSON_COUNT" -eq 0 ]; then
    echo "Processing $PDF_COUNT PDFs ..."
    python -m app.pdf_processor
else
    echo "Extracted data present ($JSON_COUNT JSON files) — skipping processing."
fi

# 3. Start the server
echo "Starting uvicorn ..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
