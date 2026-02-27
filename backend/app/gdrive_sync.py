"""
Download SOB PDFs from a shared Google Drive folder to the local PDFS_DIR.

Uses the Google Drive API v3 with a service account.
The Drive folder must be shared with the service account's client_email.

Usage (CLI):
    python -m app.gdrive_sync
    python -m app.gdrive_sync --folder-id 1vLr...  --dest /data/Pdfs
"""

import argparse
import io
import json
import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from .config import GDRIVE_FOLDER_ID, GOOGLE_SERVICE_ACCOUNT_JSON, PDFS_DIR

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _get_drive_service():
    """Build an authenticated Google Drive v3 service from the env-var JSON."""
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not set")

    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def _list_files(service, folder_id: str) -> list[dict]:
    """List all files in a Google Drive folder via the API."""
    files = []
    page_token = None
    while True:
        resp = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, size, mimeType)",
                pageSize=1000,
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def _download_file(service, file_id: str, dest_path: str) -> None:
    """Download a single file from Google Drive."""
    request = service.files().get_media(fileId=file_id)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def sync_folder(folder_id: str = GDRIVE_FOLDER_ID, dest: str = PDFS_DIR) -> dict:
    """Download every file from a Google Drive folder into *dest*.

    Returns a summary dict with counts and any errors.
    """
    os.makedirs(dest, exist_ok=True)
    summary = {"downloaded": 0, "skipped": 0, "errors": []}

    try:
        service = _get_drive_service()
    except Exception as exc:
        summary["errors"].append(str(exc))
        log.error("Google Drive auth failed: %s", exc)
        return summary

    try:
        log.info("Listing files in Google Drive folder %s", folder_id)
        files = _list_files(service, folder_id)
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
                _download_file(service, file_id, dst)
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
