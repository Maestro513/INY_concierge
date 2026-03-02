#!/usr/bin/env bash
#
# Upload extracted JSON files to Render persistent disk.
#
# Usage:
#   ADMIN_SECRET=your_secret bash upload_extracted.sh
#
# This compresses backend/extracted/ into a tar.gz and uploads it
# to the /api/admin/upload/extracted endpoint on Render.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXTRACTED_DIR="${SCRIPT_DIR}/extracted"
RENDER_URL="${RENDER_URL:-https://iny-concierge.onrender.com}"
TARBALL="/tmp/extracted_jsons.tar.gz"

if [ -z "$ADMIN_SECRET" ]; then
    echo "ERROR: Set ADMIN_SECRET environment variable first."
    echo "  export ADMIN_SECRET=your_render_admin_secret"
    exit 1
fi

if [ ! -d "$EXTRACTED_DIR" ]; then
    echo "ERROR: extracted/ directory not found at $EXTRACTED_DIR"
    exit 1
fi

JSON_COUNT=$(find "$EXTRACTED_DIR" -name '*.json' | wc -l)
echo "=== Extracted JSON Upload ==="
echo "  Directory: $EXTRACTED_DIR"
echo "  JSON files: $JSON_COUNT"
echo "  Target: $RENDER_URL/api/admin/upload/extracted"
echo ""

# Compress
echo "Compressing $JSON_COUNT JSON files..."
tar czf "$TARBALL" -C "$EXTRACTED_DIR" .
SIZE=$(du -h "$TARBALL" | cut -f1)
echo "  Archive: $TARBALL ($SIZE)"
echo ""

# Upload
echo "Uploading to Render (this may take a few minutes)..."
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${RENDER_URL}/api/admin/upload/extracted" \
    -H "X-Admin-Secret: ${ADMIN_SECRET}" \
    -F "file=@${TARBALL}" \
    --max-time 600)

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo ""
if [ "$HTTP_CODE" = "200" ]; then
    echo "SUCCESS!"
    echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
else
    echo "FAILED (HTTP $HTTP_CODE)"
    echo "$BODY"
    exit 1
fi

# Cleanup
rm -f "$TARBALL"
echo ""
echo "Done. Extracted JSONs are now on Render disk."
