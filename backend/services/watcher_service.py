from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import threading
import time
from typing import Dict, Optional, Set
from backend.config import settings
from backend.models.database import SessionLocal
from backend.models.entities import Event, IngestionAuditLog
from backend.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
IGNORED_PATTERNS = {".tmp", ".crdownload", ".part", "thumbs.db", ".ds_store"}

class WatchedFolderWorker(threading.Thread):
    def __init__(self, event_id: str, folder_path: str, poll_interval: float = 2.0):
        super().__init__(daemon=True, name=f"Watcher-{event_id[:8]}")
        self.event_id = event_id
        self.folder_path = Path(folder_path).resolve()
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self.processed_files: Set[str] = set()
        self.files_processed_count = 0
        self.error_count = 0
        self.last_scanned_at: Optional[datetime] = None

    def stop(self):
        self._stop_event.set()

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def verify_stabilization_and_lock(self, file_path: Path, max_retries: int = 4) -> bool:
        """
        File-size stabilization probing and read-lock verification.
        Ensures camera tethering software (Sony Imaging Edge, Canon EOS Utility, Nikon NX Tether, Lightroom)
        has completely written and closed the file before EventFrame ingests it.
        """
        delay = settings.FILE_STABILIZATION_DELAY
        for attempt in range(max_retries):
            if self._stop_event.is_set():
                return False
            try:
                if not file_path.exists():
                    return False
                size1 = file_path.stat().st_size
                if size1 == 0:
                    time.sleep(delay)
                    delay *= 1.5
                    continue

                time.sleep(delay)
                size2 = file_path.stat().st_size

                # Check if size stabilized
                if size1 == size2 and size2 > 0:
                    # Attempt non-blocking binary read test to verify file lock is released
                    with open(file_path, "rb") as f:
                        f.seek(0, os.SEEK_END)
                        end_pos = f.tell()
                        if end_pos > 0:
                            return True
            except (PermissionError, OSError) as e:
                logger.debug(f"File {file_path.name} locked by tethering software (attempt {attempt+1}/{max_retries}): {e}")
            except Exception as e:
                logger.warning(f"Error checking file {file_path.name}: {e}")

            time.sleep(delay)
            delay *= 1.5

        return False

    def run(self):
        logger.info(f"Started watched folder scanner for event {self.event_id} at {self.folder_path}")
        while not self._stop_event.is_set():
            self.last_scanned_at = datetime.now(timezone.utc)
            try:
                if self.folder_path.exists() and self.folder_path.is_dir():
                    # Scan directory
                    for entry in os.scandir(str(self.folder_path)):
                        if self._stop_event.is_set():
                            break
                        if not entry.is_file():
                            continue

                        name_lower = entry.name.lower()
                        ext = os.path.splitext(name_lower)[1]
                        
                        # Skip ignored temporary tethering files
                        if ext not in SUPPORTED_EXTENSIONS or any(pat in name_lower for pat in IGNORED_PATTERNS):
                            continue

                        file_path = Path(entry.path)
                        if str(file_path) in self.processed_files:
                            continue

                        # Probe stabilization and read lock
                        if not self.verify_stabilization_and_lock(file_path):
                            logger.warning(f"Skipping unstable/locked tethered file: {file_path.name}")
                            continue

                        # Ingest file
                        db = SessionLocal()
                        try:
                            photo, status = IngestionService.ingest_photo_file(
                                event_id=self.event_id,
                                file_path=file_path,
                                db=db,
                                source="watched_folder"
                            )
                            if status in ("success", "duplicate"):
                                self.processed_files.add(str(file_path))
                                if status == "success":
                                    self.files_processed_count += 1
                            else:
                                self.error_count += 1
                        except Exception as e:
                            self.error_count += 1
                            logger.error(f"Failed ingesting tethered file {file_path.name}: {e}")
                        finally:
                            db.close()
            except Exception as e:
                self.error_count += 1
                logger.error(f"Error scanning watched folder {self.folder_path}: {e}")

            # Sleep with interruptible check
            self._stop_event.wait(self.poll_interval)

        logger.info(f"Stopped watched folder scanner for event {self.event_id}")

class WatcherManager:
    """Manages active watched folder workers across all events."""

    def __init__(self):
        self._workers: Dict[str, WatchedFolderWorker] = {}
        self._lock = threading.Lock()

    def start_watcher(self, event_id: str, folder_path: str, poll_interval: float = 2.0) -> bool:
        with self._lock:
            # If already running, stop previous worker first
            if event_id in self._workers:
                prev = self._workers[event_id]
                prev.stop()
                prev.join(timeout=2.0)

            worker = WatchedFolderWorker(event_id, folder_path, poll_interval)
            self._workers[event_id] = worker
            worker.start()
            return True

    def stop_watcher(self, event_id: str) -> bool:
        with self._lock:
            if event_id in self._workers:
                worker = self._workers[event_id]
                worker.stop()
                worker.join(timeout=2.0)
                del self._workers[event_id]
                return True
            return False

    def is_running(self, event_id: str) -> bool:
        with self._lock:
            worker = self._workers.get(event_id)
            return worker is not None and worker.is_alive()

    def get_status(self, event_id: str) -> dict:
        with self._lock:
            worker = self._workers.get(event_id)
            if worker and worker.is_alive():
                return {
                    "event_id": event_id,
                    "watched_folder": str(worker.folder_path),
                    "is_active": True,
                    "last_scanned_at": worker.last_scanned_at,
                    "files_processed": worker.files_processed_count,
                    "errors": worker.error_count,
                }
            return {
                "event_id": event_id,
                "watched_folder": None,
                "is_active": False,
                "last_scanned_at": None,
                "files_processed": 0,
                "errors": 0,
            }

watcher_manager = WatcherManager()
