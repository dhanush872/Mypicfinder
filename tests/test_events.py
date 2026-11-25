import pytest
from backend.models.entities import Event

def test_create_and_list_events(client, auth_headers):
    # 1. Create Event
    create_resp = client.post("/api/events", headers=auth_headers, json={
        "title": "Summer Festival 2026",
        "venue": "Bayside Park",
        "pin_code": "4321",
        "strict_selfie_mode": True,
        "watched_folder": "/path/to/tether"
    })
    assert create_resp.status_code == 201
    data = create_resp.json()
    assert data["title"] == "Summer Festival 2026"
    assert data["venue"] == "Bayside Park"
    assert data["pin_code"] == "4321"
    assert data["strict_selfie_mode"] is True
    assert len(data["guest_token"]) >= 32
    event_id = data["id"]

    # 2. List Events
    list_resp = client.get("/api/events", headers=auth_headers)
    assert list_resp.status_code == 200
    events = list_resp.json()
    assert len(events) >= 1
    assert any(e["id"] == event_id for e in events)

    # 3. Get Event by ID
    get_resp = client.get(f"/api/events/{event_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == event_id

def test_update_event(client, auth_headers, test_event):
    update_resp = client.patch(f"/api/events/{test_event.id}", headers=auth_headers, json={
        "title": "Updated Gala Title",
        "pin_code": "9999",
        "strict_selfie_mode": True
    })
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["title"] == "Updated Gala Title"
    assert updated["pin_code"] == "9999"
    assert updated["strict_selfie_mode"] is True

def test_regenerate_guest_token_kill_switch(client, auth_headers, test_event):
    old_token = test_event.guest_token
    regen_resp = client.post(f"/api/events/{test_event.id}/regenerate-token", headers=auth_headers)
    assert regen_resp.status_code == 200
    new_token = regen_resp.json()["guest_token"]
    assert new_token != old_token
    assert len(new_token) >= 32

    # Old token fails guest info lookup
    old_guest_resp = client.get(f"/api/guest/info?token={old_token}")
    assert old_guest_resp.status_code in (401, 404)

    # New token succeeds
    new_guest_resp = client.get(f"/api/guest/info?token={new_token}")
    assert new_guest_resp.status_code == 200

def test_qr_generation_png_and_svg(client, auth_headers, test_event):
    # PNG QR
    png_resp = client.get(f"/api/events/{test_event.id}/qr.png", headers=auth_headers)
    assert png_resp.status_code == 200
    assert png_resp.headers["content-type"] == "image/png"
    # Verify PNG magic bytes
    assert png_resp.content.startswith(b"\x89PNG\r\n\x1a\n")

    # SVG QR
    svg_resp = client.get(f"/api/events/{test_event.id}/qr.svg", headers=auth_headers)
    assert svg_resp.status_code == 200
    assert "svg" in svg_resp.headers["content-type"]
    assert svg_resp.text.startswith("<svg")
    assert "</svg>" in svg_resp.text
