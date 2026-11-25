import time
import pytest
from backend.auth.security import (
    create_access_token,
    decode_access_token,
    generate_guest_token,
    hash_password,
    verify_password,
)
from backend.models.entities import User

def test_password_hashing():
    pw = "superSecretVenuePassword2026!"
    hashed = hash_password(pw)
    assert hashed.startswith("pbkdf2_sha256$100000$")
    assert verify_password(pw, hashed) is True
    assert verify_password("wrongPassword", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(pw, "invalid_format") is False

def test_jwt_token_creation_and_validation():
    data = {"sub": "user-1234", "email": "test@eventframe.local"}
    token = create_access_token(data, expires_delta_seconds=60)
    assert token.count(".") == 2

    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-1234"
    assert payload["email"] == "test@eventframe.local"
    assert "exp" in payload

def test_jwt_token_expiration():
    data = {"sub": "user-expired"}
    token = create_access_token(data, expires_delta_seconds=-10)
    payload = decode_access_token(token)
    assert payload is None

def test_jwt_tampered_signature():
    token = create_access_token({"sub": "user-valid"})
    parts = token.split(".")
    tampered_sig = parts[2][:-4] + "xxxx"
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"
    assert decode_access_token(tampered_token) is None

def test_guest_token_entropy():
    tokens = {generate_guest_token() for _ in range(100)}
    assert len(tokens) == 100
    for tok in tokens:
        assert len(tok) >= 40

def test_auth_endpoints_register_and_login(client):
    email = "photographer_new@eventframe.local"
    # 1. Register
    reg_resp = client.post("/api/auth/register", json={
        "email": email,
        "password": "validPassword123",
        "full_name": "Jordan Smith"
    })
    assert reg_resp.status_code == 201
    reg_data = reg_resp.json()
    assert reg_data["email"] == email
    assert reg_data["full_name"] == "Jordan Smith"
    assert "id" in reg_data

    # 2. Duplicate registration fails
    dup_resp = client.post("/api/auth/register", json={
        "email": email,
        "password": "validPassword123"
    })
    assert dup_resp.status_code == 400

    # 3. Login
    login_resp = client.post("/api/auth/login", json={
        "email": email,
        "password": "validPassword123"
    })
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    token = token_data["access_token"]

    # 4. Access /api/auth/me via Bearer
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email

    # 5. Access /api/auth/me via query param ?token=
    me_query_resp = client.get(f"/api/auth/me?token={token}")
    assert me_query_resp.status_code == 200
    assert me_query_resp.json()["email"] == email
