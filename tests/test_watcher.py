from pathlib import Path
import time
import pytest
from backend.services.watcher_service import WatchedFolderWorker, watcher_manager
from tests.conftest import make_test_image

def test_watched_folder_worker_stabilization(test_temp_dir):
    tether_dir = test_temp_dir / "tether_inbox"
    tether_dir.mkdir(parents=True, exist_ok=True)

    worker = WatchedFolderWorker("dummy-event-id", str(tether_dir), poll_interval=0.1)

    # 1. Non-existent file
    assert worker.verify_stabilization_and_lock(tether_dir / "nonexistent.jpg") is False

    # 2. Empty 0-byte file
    empty_file = tether_dir / "empty.jpg"
    empty_file.write_bytes(b"")
    assert worker.verify_stabilization_and_lock(empty_file, max_retries=2) is False

    # 3. Stable, completely written file
    img_bytes = make_test_image(200, 200, draw_face=True)
    complete_file = tether_dir / "stable_shot.jpg"
    complete_file.write_bytes(img_bytes)
    assert worker.verify_stabilization_and_lock(complete_file) is True

def test_watcher_manager_lifecycle(test_temp_dir):
    tether_dir = test_temp_dir / "tether_lifecycle"
    tether_dir.mkdir(parents=True, exist_ok=True)
    event_id = "test-event-lifecycle-1"

    # Start watcher
    started = watcher_manager.start_watcher(event_id, str(tether_dir), poll_interval=0.5)
    assert started is True
    assert watcher_manager.is_running(event_id) is True

    status = watcher_manager.get_status(event_id)
    assert status["is_active"] is True
    assert status["watched_folder"] == str(tether_dir.resolve())

    # Stop watcher
    stopped = watcher_manager.stop_watcher(event_id)
    assert stopped is True
    assert watcher_manager.is_running(event_id) is False

    status_stopped = watcher_manager.get_status(event_id)
    assert status_stopped["is_active"] is False
