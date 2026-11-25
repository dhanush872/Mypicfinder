#!/usr/bin/env python3
"""
Automated validation and packaging script for EventFrame.
1. Executes pytest test suite.
2. Verifies manifest and static asset integrity.
3. Packages a clean distributable ZIP archive without cache or temp files.
"""
import os
from pathlib import Path
import subprocess
import sys
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_PATTERNS = {
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    ".git",
    "eventframe.db",
    "eventframe.db-wal",
    "eventframe.db-shm",
    "eventframe_dist.zip",
    ".DS_Store",
    "Thumbs.db",
}

def verify_manifest_integrity() -> bool:
    print("[*] Verifying frontend manifest and assets integrity...")
    manifest_path = PROJECT_ROOT / "frontend" / "manifest.json"
    sw_path = PROJECT_ROOT / "frontend" / "sw.js"
    guest_path = PROJECT_ROOT / "frontend" / "guest.html"
    index_path = PROJECT_ROOT / "frontend" / "index.html"
    css_path = PROJECT_ROOT / "frontend" / "css" / "styles.css"

    for p in (manifest_path, sw_path, guest_path, index_path, css_path):
        if not p.exists() or p.stat().st_size == 0:
            print(f"[✗] Manifest/Asset integrity failed: Missing or empty {p.relative_to(PROJECT_ROOT)}")
            return False

    print("[✓] Frontend manifest and core assets verified successfully.")
    return True

def run_tests() -> bool:
    print("\n[*] Executing full pytest test suite...")
    cmd = [sys.executable, "-m", "pytest", "tests", "-v", "--durations=5"]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print("[✗] Test suite failed.")
        return False
    print("[✓] All automated tests passed successfully.")
    return True

def package_dist_zip() -> Path:
    zip_path = PROJECT_ROOT / "eventframe_dist.zip"
    if zip_path.exists():
        zip_path.unlink()

    print(f"\n[*] Packaging clean distributable archive: {zip_path.name}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(str(PROJECT_ROOT)):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDE_PATTERNS and not d.startswith(".")]
            
            for file in files:
                if file in EXCLUDE_PATTERNS or file.endswith(".pyc") or file.endswith(".zip"):
                    continue
                file_path = Path(root) / file
                # Skip files inside storage runtime subdirs if any exist
                rel_parts = file_path.relative_to(PROJECT_ROOT).parts
                if len(rel_parts) > 1 and rel_parts[0] == "storage" and rel_parts[1] in ("originals", "previews", "thumbnails"):
                    continue

                archive_name = str(file_path.relative_to(PROJECT_ROOT))
                zf.write(file_path, archive_name)

    print(f"[✓] Distributable created: {zip_path} ({round(zip_path.stat().st_size / 1024, 2)} KB)")
    return zip_path

def main():
    print("=" * 60)
    print("  EventFrame Build & Verification Pipeline")
    print("=" * 60)

    if not verify_manifest_integrity():
        sys.exit(1)

    if not run_tests():
        sys.exit(1)

    dist_zip = package_dist_zip()
    print("\n" + "=" * 60)
    print("  🎉 All Checks Passed! Production Dist Ready.")
    print("=" * 60)

if __name__ == "__main__":
    main()
