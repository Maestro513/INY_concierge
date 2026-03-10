#!/usr/bin/env bash
set -e

echo "=== InsuranceNYou Backend Startup ==="

EXTRACTED=${EXTRACTED_DIR:-extracted}
JSON_COUNT=$(find "$EXTRACTED" -iname '*.json' 2>/dev/null | wc -l)

# 1. If extracted JSONs already exist (persistent disk), skip download + processing
if [ "$JSON_COUNT" -gt 0 ]; then
    echo "Extracted data present ($JSON_COUNT JSON files) — ready to serve."
else
    echo "No extracted data found — checking for local PDFs ..."

    PDF_COUNT=$(find "${PDFS_DIR:-pdf Updated}" -iname '*.pdf' 2>/dev/null | wc -l)
    if [ "$PDF_COUNT" -gt 0 ]; then
        echo "Processing $PDF_COUNT PDFs ..."
        python -m app.pdf_processor
    else
        echo "WARNING: No PDFs found and no extracted data — AI features will be limited."
    fi
fi

# 2. Build CMS benefits DB if missing
CMS_DB="${CMS_DB_PATH:-cms_benefits.db}"
if [ ! -f "$CMS_DB" ]; then
    CMS_DIR="${CMS_DIR:-pdfs/CMS}"
    if [ -d "$CMS_DIR" ]; then
        echo "Building CMS benefits database from $CMS_DIR ..."
        python cms_import.py --cms-dir "$CMS_DIR" --db "$CMS_DB"
    else
        echo "WARNING: CMS directory $CMS_DIR not found — benefits lookup will be unavailable."
    fi
else
    echo "CMS benefits database present — skipping import."
fi

# 3. Run database migrations (PR14: replaces fragile CREATE IF NOT EXISTS)
echo "Running database migrations ..."
python -m app.db_migrate

# 3. Start the server
echo "Starting uvicorn ..."
WORKERS="${WEB_CONCURRENCY:-4}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "$WORKERS" \
     --timeout-graceful-shutdown 30 --timeout-keep-alive 75
