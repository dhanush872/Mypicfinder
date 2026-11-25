import pytest
from backend.models.entities import Event
from tests.conftest import make_test_image

def test_guest_info_endpoint(client, test_event):
    resp = client.get(f"/api/guest/info?token={test_event.guest_token}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == test_event.title
    assert data["venue"] == test_event.venue
    assert data["has_pin"] is False
    assert data["strict_selfie_mode"] is False
    # Ensure photographer internal details are not leaked
    assert "owner_id" not in data
    assert "watched_folder" not in data

def test_guest_pin_protection(client, db_session, test_user):
    pin_event = Event(
        owner_id=test_user.id,
        title="VIP Gala",
        slug="vip-gala",
        guest_token="vip_token_123456789012345678901234",
        pin_code="1234",
        strict_selfie_mode=False
    )
    db_session.add(pin_event)
    db_session.commit()

    # 1. Info shows has_pin = True
    info = client.get(f"/api/guest/info?token={pin_event.guest_token}").json()
    assert info["has_pin"] is True

    # 2. Verify PIN endpoint: incorrect vs correct
    bad_pin = client.post(
        f"/api/guest/verify-pin?token={pin_event.guest_token}",
        json={"pin_code": "0000"}
    )
    assert bad_pin.status_code == 400

    good_pin = client.post(
        f"/api/guest/verify-pin?token={pin_event.guest_token}",
        json={"pin_code": "1234"}
    )
    assert good_pin.status_code == 200
    assert good_pin.json()["verified"] is True

    # 3. Gallery access without PIN fails with 401
    no_pin_gallery = client.get(f"/api/guest/gallery?token={pin_event.guest_token}")
    assert no_pin_gallery.status_code == 401

    # 4. Gallery access with PIN succeeds
    pin_gallery = client.get(
        f"/api/guest/gallery?token={pin_event.guest_token}&pin=1234"
    )
    assert pin_gallery.status_code == 200

    # 5. Gallery access with X-Guest-PIN header succeeds
    header_gallery = client.get(
        f"/api/guest/gallery?token={pin_event.guest_token}",
        headers={"X-Guest-PIN": "1234"}
    )
    assert header_gallery.status_code == 200

def test_strict_selfie_mode_blocks_gallery(client, db_session, test_user):
    strict_event = Event(
        owner_id=test_user.id,
        title="Private Confidential Event",
        slug="strict-event",
        guest_token="strict_token_123456789012345678901234",
        strict_selfie_mode=True
    )
    db_session.add(strict_event)
    db_session.commit()

    # Public gallery must be strictly blocked (403 Forbidden)
    resp = client.get(f"/api/guest/gallery?token={strict_event.guest_token}")
    assert resp.status_code == 403
    assert "strict selfie-only mode" in resp.json()["detail"].lower()

def test_protected_media_delivery(client, auth_headers, test_event):
    # 1. Ingest photo
    img_bytes = make_test_image(300, 300, draw_face=True)
    upload_resp = client.post(
        f"/api/events/{test_event.id}/photos/upload",
        headers=auth_headers,
        files={"files": ("media_test.jpg", img_bytes, "image/jpeg")}
    )
    assert upload_resp.status_code == 201
    photo_id = upload_resp.json()[0]["id"]

    # 2. Thumbnail with guest token -> 200
    thumb_resp = client.get(f"/api/media/{photo_id}/thumbnail?token={test_event.guest_token}")
    assert thumb_resp.status_code == 200
    assert thumb_resp.headers["content-type"] == "image/jpeg"
    assert "private" in thumb_resp.headers["cache-control"]

    # 3. Preview with guest token -> 200
    preview_resp = client.get(f"/api/media/{photo_id}/preview?token={test_event.guest_token}")
    assert preview_resp.status_code == 200

    # 4. Original download with guest token -> 200 with attachment
    orig_resp = client.get(f"/api/media/{photo_id}/original?token={test_event.guest_token}")
    assert orig_resp.status_code == 200
    assert "attachment" in orig_resp.headers["content-disposition"]

    # 5. Media access without token -> 401
    unauth_resp = client.get(f"/api/media/{photo_id}/thumbnail")
    assert unauth_resp.status_code == 401

    # 6. Media access with invalid token -> 403
    forbidden_resp = client.get(f"/api/media/{photo_id}/thumbnail?token=invalid_random_token")
    assert forbidden_resp.status_code == 403
