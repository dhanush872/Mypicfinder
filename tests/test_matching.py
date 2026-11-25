import io
import os
import numpy as np
from PIL import Image
import pytest
from backend.config import settings
from backend.matchers import get_face_matcher
from backend.matchers.base import FaceDescriptor
from backend.matchers.deep_matcher import DeepFaceMatcher
from backend.matchers.local_matcher import LocalFeatureFaceMatcher
from backend.models.entities import Event
from backend.services.face_service import FaceService
from tests.conftest import make_test_image

def test_local_face_matcher_properties():
    matcher = LocalFeatureFaceMatcher()
    assert matcher.dimension == 128
    assert matcher.name == "local_feature_matcher"

    # Test detection on synthetic face image
    img_bytes = make_test_image(200, 200, draw_face=True)
    with Image.open(io.BytesIO(img_bytes)) as pil_img:
        faces = matcher.detect_and_extract(pil_img)
        assert len(faces) >= 1
        for f in faces:
            assert len(f.embedding) == 128
            # Verify L2 norm is ~1.0
            norm = np.linalg.norm(f.embedding)
            assert np.isclose(norm, 1.0, atol=1e-3)
            assert f.confidence > 0.0

def test_cosine_similarity_computation():
    matcher = LocalFeatureFaceMatcher()
    vec1 = np.random.randn(128).astype(np.float32)
    vec1 /= np.linalg.norm(vec1)

    candidates = np.stack([
        vec1,                   # Exact match -> sim = 1.0
        -vec1,                  # Opposite -> sim = -1.0
        np.zeros(128, dtype=np.float32)  # Zero vector
    ])

    sims = matcher.compute_similarity(vec1, candidates)
    assert np.isclose(sims[0], 1.0, atol=1e-3)
    assert np.isclose(sims[1], -1.0, atol=1e-3)

def test_deep_face_matcher_fallback():
    deep = DeepFaceMatcher()
    assert deep.dimension in (128, 512)
    # Should run gracefully even without external ONNX weights
    img_bytes = make_test_image(200, 200, draw_face=True)
    with Image.open(io.BytesIO(img_bytes)) as pil_img:
        faces = deep.detect_and_extract(pil_img)
        assert len(faces) >= 1

def test_biometric_privacy_consent_enforcement(client, test_event):
    img_bytes = make_test_image(200, 200, draw_face=True)

    # 1. Search without biometric consent -> MUST FAIL with 400
    resp_no_consent = client.post(
        f"/api/guest/selfie-search?token={test_event.guest_token}",
        data={"biometric_consent": "false"},
        files={"selfie": ("selfie.jpg", img_bytes, "image/jpeg")}
    )
    assert resp_no_consent.status_code == 400
    assert "consent is required" in resp_no_consent.json()["detail"].lower()

    # 2. Search with consent -> SUCCEEDS
    resp_with_consent = client.post(
        f"/api/guest/selfie-search?token={test_event.guest_token}",
        data={"biometric_consent": "true"},
        files={"selfie": ("selfie.jpg", img_bytes, "image/jpeg")}
    )
    assert resp_with_consent.status_code == 200
    res_data = resp_with_consent.json()
    assert "match_count" in res_data
    assert "latency_ms" in res_data
    assert res_data["latency_ms"] >= 0.0

def test_volatile_ram_guarantee(client, test_event):
    """Verify that guest selfies are NEVER saved to storage or disk."""
    initial_files = set()
    for root, _, files in os.walk(str(settings.STORAGE_DIR)):
        for f in files:
            initial_files.add(f)

    # Perform selfie search
    selfie_bytes = make_test_image(250, 250, draw_face=True)
    resp = client.post(
        f"/api/guest/selfie-search?token={test_event.guest_token}",
        data={"biometric_consent": "true"},
        files={"selfie": ("guest_volatile_selfie.jpg", selfie_bytes, "image/jpeg")}
    )
    assert resp.status_code == 200

    # Ensure no new files appeared on disk
    current_files = set()
    for root, _, files in os.walk(str(settings.STORAGE_DIR)):
        for f in files:
            current_files.add(f)

    assert initial_files == current_files

def test_event_isolation_scoping(client, auth_headers, db_session, test_user):
    # Create Event A and upload Photo A
    ev_a = Event(
        owner_id=test_user.id,
        title="Event A",
        slug="event-a",
        guest_token="token_a_12345678901234567890123456",
        strict_selfie_mode=False
    )
    # Create Event B and upload Photo B
    ev_b = Event(
        owner_id=test_user.id,
        title="Event B",
        slug="event-b",
        guest_token="token_b_12345678901234567890123456",
        strict_selfie_mode=False
    )
    db_session.add_all([ev_a, ev_b])
    db_session.commit()

    img_bytes = make_test_image(300, 300, draw_face=True)
    resp_a = client.post(
        f"/api/events/{ev_a.id}/photos/upload",
        headers=auth_headers,
        files={"files": ("photo_a.jpg", img_bytes, "image/jpeg")}
    )
    assert resp_a.status_code == 201

    # Search Event B using the face from Photo A
    search_b = client.post(
        f"/api/guest/selfie-search?token={ev_b.guest_token}",
        data={"biometric_consent": "true"},
        files={"selfie": ("query.jpg", img_bytes, "image/jpeg")}
    )
    assert search_b.status_code == 200
    # Cross-event searches must be structurally impossible (returns 0 matches)
    assert search_b.json()["match_count"] == 0
