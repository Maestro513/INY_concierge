"""
Download SOB PDFs from a shared Google Drive folder to the local pdfs/ directory.

Skips download if PDFs already exist on disk (persistent Render disk).

Env vars:
  GDRIVE_FOLDER_ID  — Google Drive folder ID (from the share URL)
  PDFS_DIR          — destination directory (default: backend/pdfs)
"""

import os
import sys
import glob

PDFS_DIR = os.getenv("PDFS_DIR", os.path.join(os.path.dirname(__file__), "pdfs"))
FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "")


def pdfs_already_exist() -> bool:
    """Check if any PDFs are already on disk."""
    if not os.path.isdir(PDFS_DIR):
        return False
    for root, _, files in os.walk(PDFS_DIR):
        if any(f.lower().endswith(".pdf") for f in files):
            return True
    return False


def download():
    if not FOLDER_ID:
        print("GDRIVE_FOLDER_ID not set — skipping PDF download.")
        return

    if pdfs_already_exist():
        count = sum(
            1 for r, _, fs in os.walk(PDFS_DIR)
            for f in fs if f.lower().endswith(".pdf")
        )
        print(f"PDFs already on disk ({count} files in {PDFS_DIR}) — skipping download.")
        return

    print(f"Downloading PDFs from Google Drive folder {FOLDER_ID} ...")
    os.makedirs(PDFS_DIR, exist_ok=True)

    import gdown
    url = f"https://drive.google.com/drive/folders/{FOLDER_ID}"
    gdown.download_folder(url, output=PDFS_DIR, quiet=False)

    count = sum(
        1 for r, _, fs in os.walk(PDFS_DIR)
        for f in fs if f.lower().endswith(".pdf")
    )
    print(f"Done — {count} PDFs downloaded to {PDFS_DIR}")


if __name__ == "__main__":
    download()
