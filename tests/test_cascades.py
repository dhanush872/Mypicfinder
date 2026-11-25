from pathlib import Path
import pytest
from backend.models.entities import Event, FaceEmbedding, IngestionAuditLog, Photo
from backend.services.storage_service import StorageService
from tests.conftest import make_test_image

def test_single_photo_deletion_cascade(client, auth_headers, test_event, db_session):
    # 1. Upload photo
    img_bytes = make_test_image(400, 400, draw_face=True)
    resp = client.post(
        f"/api/events/{test_event.id}/photos/upload",
        headers=auth_headers,
        files={"files": ("photo_cascade.jpg", img_bytes, "image/jpeg")}
    )
    assert resp.status_code == 201
    photo_id = resp.json()[0]["id"]

    # Verify photo and embeddings in DB
    photo = db_session.query(Photo).filter(Photo.id == photo_id).first()
    assert photo is not None
    faces = db_session.query(FaceEmbedding).filter(FaceEmbedding.photo_id == photo_id).all()
    assert len(faces) >= 1

    orig_path = StorageService.resolve_photo_path(photo.file_path)
    prev_path = StorageService.resolve_photo_path(photo.preview_path)
    thumb_path = StorageService.resolve_photo_path(photo.thumbnail_path)
    assert orig_path and orig_path.exists()
    assert prev_path and prev_path.exists()
    assert thumb_path and thumb_path.exists()

    # 2. Delete photo
    del_resp = client.delete(f"/api/events/{test_event.id}/photos/{photo_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    # 3. Verify DB purge
    assert db_session.query(Photo).filter(Photo.id == photo_id).first() is None
    assert db_session.query(FaceEmbedding).filter(FaceEmbedding.photo_id == photo_id).count() == 0

    # 4. Verify disk file purge
    assert not orig_path.exists()
    assert not prev_path.exists()
    assert not thumb_path.exists()

def test_event_full_cascade_purge(client, auth_headers, test_event, db_session):
    # 1. Ingest photo into event
    img_bytes = make_test_image(500, 500, draw_face=True)
    resp = client.post(
        f"/api/events/{test_event.id}/photos/upload",
        headers=auth_headers,
        files={"files": ("gala_shot.jpg", img_bytes, "image/jpeg")}
    )
    assert resp.status_code == 201
    photo_id = resp.json()[0]["id"]

    photo = db_session.query(Photo).filter(Photo.id == photo_id).first()
    assert photo is not None
    orig_path = StorageService.resolve_photo_path(photo.file_path)
    assert orig_path and orig_path.exists()

    # 2. Delete entire event
    del_event_resp = client.delete(f"/api/events/{test_event.id}", headers=auth_headers)
    assert del_event_resp.status_code == 204

    # 3. Verify Event, Photos, Faces, and Logs are purged from DB
    assert db_session.query(Event).filter(Event.id == test_event.id).first() is None
    assert db_session.query(Photo).filter(Photo.event_id == test_event.id).count() == 0
    assert db_session.query(FaceEmbedding).filter(FaceEmbedding.event_id == test_event.id).count() == 0
    assert db_session.query(IngestionAuditLog).filter(IngestionAuditLog.event_id == test_event.id).count() == 0

    # 4. Verify disk event directory is purged
    assert not orig_path.exists()
