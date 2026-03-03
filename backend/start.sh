#!/usr/bin/env bash
set -e

echo "=== InsuranceNYou Backend Startup ==="

EXTRACTED=${EXTRACTED_DIR:-extracted}
JSON_COUNT=$(find "$EXTRACTED" -iname '*.json' 2>/dev/null | wc -l)

# 1. If extracted JSONs already exist (persistent disk), skip download + processing
if [ "$JSON_COUNT" -gt 0 ]; then
    echo "Extracted data present ($JSON_COUNT JSON files) — ready to serve."
else
    # Try downloading PDFs; don't crash startup if it fails
    echo "No extracted data found — attempting PDF download + processing ..."
    python download_pdfs.py || echo "WARNING: PDF download failed (non-fatal)"

    PDF_COUNT=$(find "${PDFS_DIR:-pdf Updated}" -iname '*.pdf' 2>/dev/null | wc -l)
    if [ "$PDF_COUNT" -gt 0 ]; then
        echo "Processing $PDF_COUNT PDFs ..."
        python -m app.pdf_processor
    else
        echo "WARNING: No PDFs found and no extracted data — AI features will be limited."
    fi
fi

# 2. Start the server
echo "Starting uvicorn ..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
