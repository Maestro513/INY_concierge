"""
Download SOB PDFs from a shared Google Drive folder to the local PDFS_DIR.

Uses the Google Drive API v3 with an API key (no OAuth/service-account needed).
The folder must be shared as "Anyone with the link → Viewer" (or broader).

Usage (CLI):
    python -m app.gdrive_sync
    python -m app.gdrive_sync --folder-id 1vLr...  --dest /data/Pdfs
"""

import argparse
import logging
import os

import requests

from .config import GDRIVE_FOLDER_ID, GOOGLE_API_KEY, PDFS_DIR

log = logging.getLogger(__name__)

DRIVE_LIST_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_DOWNLOAD_URL = "https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={key}"


def _list_files(folder_id: str, api_key: str) -> list[dict]:
    """List all files in a Google Drive folder via the API."""
    files = []
    page_token = None
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "key": api_key,
            "fields": "nextPageToken, files(id, name, size, mimeType)",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(DRIVE_LIST_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        files.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return files


def _download_file(file_id: str, api_key: str, dest_path: str) -> None:
    """Download a single file from Google Drive."""
    url = DRIVE_DOWNLOAD_URL.format(file_id=file_id, key=api_key)
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def sync_folder(folder_id: str = GDRIVE_FOLDER_ID, dest: str = PDFS_DIR) -> dict:
    """Download every file from a Google Drive folder into *dest*.

    Returns a summary dict with counts and any errors.
    """
    os.makedirs(dest, exist_ok=True)
    summary = {"downloaded": 0, "skipped": 0, "errors": []}

    if not GOOGLE_API_KEY:
        summary["errors"].append("GOOGLE_API_KEY not configured")
        return summary

    try:
        log.info("Listing files in Google Drive folder %s", folder_id)
        files = _list_files(folder_id, GOOGLE_API_KEY)
        log.info("Found %d files in Drive folder", len(files))

        for f in files:
            fname = f["name"]
            file_id = f["id"]
            remote_size = int(f.get("size", 0))
            dst = os.path.join(dest, fname)

            try:
                # Skip if identical file already exists (same size)
                if os.path.isfile(dst) and os.path.getsize(dst) == remote_size:
                    summary["skipped"] += 1
                    log.debug("Skipped (unchanged): %s", fname)
                    continue

                log.info("Downloading: %s (%s bytes)", fname, remote_size)
                _download_file(file_id, GOOGLE_API_KEY, dst)
                summary["downloaded"] += 1
                log.info("Saved: %s", fname)

            except Exception as exc:
                summary["errors"].append(f"{fname}: {exc}")
                log.exception("Failed to download %s", fname)

    except Exception as exc:
        summary["errors"].append(str(exc))
        log.exception("Google Drive sync failed")

    log.info(
        "Sync complete: %d downloaded, %d skipped, %d errors",
        summary["downloaded"],
        summary["skipped"],
        len(summary["errors"]),
    )
    return summary


# ── CLI entry-point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Sync SOB PDFs from Google Drive")
    parser.add_argument("--folder-id", default=GDRIVE_FOLDER_ID)
    parser.add_argument("--dest", default=PDFS_DIR)
    args = parser.parse_args()

    result = sync_folder(args.folder_id, args.dest)
    print(result)
