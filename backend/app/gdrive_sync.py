"""
Download SOB PDFs from a shared Google Drive folder to the local PDFS_DIR.

Usage (CLI):
    python -m app.gdrive_sync              # uses defaults from config
    python -m app.gdrive_sync --folder-id 1vLr...  --dest /data/Pdfs

The Google Drive folder must be shared as "Anyone with the link → Viewer".
"""

import argparse
import logging
import os
import shutil
import tempfile

import gdown

from .config import GDRIVE_FOLDER_ID, PDFS_DIR

log = logging.getLogger(__name__)


def sync_folder(folder_id: str = GDRIVE_FOLDER_ID, dest: str = PDFS_DIR) -> dict:
    """Download every file from a Google Drive folder into *dest*.

    Returns a summary dict with counts and any errors.
    """
    url = f"https://drive.google.com/drive/folders/{folder_id}"
    os.makedirs(dest, exist_ok=True)

    # gdown.download_folder downloads into a temp dir, then we merge
    tmp = tempfile.mkdtemp(prefix="gdrive_sync_")
    summary = {"downloaded": 0, "skipped": 0, "errors": []}

    try:
        log.info("Downloading Google Drive folder %s → %s", folder_id, tmp)
        paths = gdown.download_folder(
            url=url,
            output=tmp,
            quiet=False,
            remaining_ok=True,  # don't fail on quota warnings
        )
        if paths is None:
            summary["errors"].append("gdown returned None – is the folder shared publicly?")
            return summary

        # Move downloaded files into dest, preserving subfolder structure
        for root, _dirs, files in os.walk(tmp):
            for fname in files:
                src = os.path.join(root, fname)
                rel = os.path.relpath(src, tmp)
                dst = os.path.join(dest, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)

                # Skip if identical file already exists (same size)
                if os.path.isfile(dst) and os.path.getsize(dst) == os.path.getsize(src):
                    summary["skipped"] += 1
                    log.debug("Skipped (unchanged): %s", rel)
                    continue

                shutil.move(src, dst)
                summary["downloaded"] += 1
                log.info("Saved: %s", rel)

    except Exception as exc:
        summary["errors"].append(str(exc))
        log.exception("Google Drive sync failed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

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
