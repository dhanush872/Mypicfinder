from pathlib import Path
from PIL import Image
import pytest
from backend.models.entities import IngestionAuditLog, Photo
from backend.services.storage_service import StorageService
from tests.conftest import make_test_image

def test_photo_upload_and_deduplication(client, auth_headers, test_event, db_session):
    img_bytes = make_test_image(300, 300, draw_face=True)

    # 1. First upload -> Success
    resp1 = client.post(
        f"/api/events/{test_event.id}/photos/upload",
        headers=auth_headers,
        files={"files": ("portrait.jpg", img_bytes, "image/jpeg")}
    )
    assert resp1.status_code == 201
    photos1 = resp1.json()
    assert len(photos1) == 1
    photo_id = photos1[0]["id"]
    assert photos1[0]["filename"] == "portrait.jpg"

    # 2. Re-upload identical bytes -> Content Deduplication
    resp2 = client.post(
        f"/api/events/{test_event.id}/photos/upload",
        headers=auth_headers,
        files={"files": ("duplicate_name.jpg", img_bytes, "image/jpeg")}
    )
    assert resp2.status_code == 201
    photos2 = resp2.json()
    # Deduplicated returns existing photo entity
    assert len(photos2) == 1
    assert photos2[0]["id"] == photo_id

    # Verify audit log recorded duplicate
    dup_logs = db_session.query(IngestionAuditLog).filter(
        IngestionAuditLog.event_id == test_event.id,
        IngestionAuditLog.status == "duplicate"
    ).all()
    assert len(dup_logs) >= 1

def test_derivative_generation_dimensions(client, auth_headers, test_event, db_session):
    # Upload 2000x1200 image
    img_bytes = make_test_image(2000, 1200, draw_face=True)
    resp = client.post(
        f"/api/events/{test_event.id}/photos/upload",
        headers=auth_headers,
        files={"files": ("large_image.jpg", img_bytes, "image/jpeg")}
    )
    assert resp.status_code == 201
    p_data = resp.json()[0]

    photo = db_session.query(Photo).filter(Photo.id == p_data["id"]).first()
    prev_path = StorageService.resolve_photo_path(photo.preview_path)
    thumb_path = StorageService.resolve_photo_path(photo.thumbnail_path)

    with Image.open(prev_path) as p_img:
        assert max(p_img.size) <= 1600

    with Image.open(thumb_path) as t_img:
        assert max(t_img.size) <= 400

def test_path_traversal_sanitization(test_temp_dir):
    base = test_temp_dir / "safe_dir"
    base.mkdir(parents=True, exist_ok=True)

    # Valid relative subpath
    safe_path = StorageService.sanitize_path(base, "sub/file.jpg")
    assert safe_path == (base / "sub" / "file.jpg").resolve()

    # Malicious traversal attempts must raise ValueError
    with pytest.raises(ValueError):
        StorageService.sanitize_path(base, "../../../etc/passwd")

    with pytest.raises(ValueError):
        StorageService.sanitize_path(base, "sub/../../../../windows/system32/cmd.exe")
