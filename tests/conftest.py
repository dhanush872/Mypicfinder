import asyncio
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException, Response
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw
import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from backend.auth.dependencies import (
    decode_access_token,
    get_guest_event,
    verify_media_access,
)
from backend.auth.security import create_access_token, hash_password
from backend.config import settings
from backend.models.database import Base, get_db
from backend.models.entities import Event, User

# Direct function imports to prevent package namespace collisions
from backend.routers.auth_router import (
    get_me as auth_get_me,
    login as auth_login,
    register as auth_register,
)
from backend.routers.events_router import (
    create_event as events_create,
    delete_event as events_delete,
    get_audit_logs as events_get_audit_logs,
    get_event as events_get,
    get_qr_png as events_get_qr_png,
    get_qr_svg as events_get_qr_svg,
    list_events as events_list,
    regenerate_guest_token as events_regenerate_token,
    update_event as events_update,
)
from backend.routers.guest_router import (
    get_guest_event_info as guest_get_info,
    get_guest_gallery as guest_get_gallery,
    search_photos_by_selfie as guest_search_selfie,
    verify_pin as guest_verify_pin,
)
from backend.routers.media_router import (
    get_original as media_get_original,
    get_preview as media_get_preview,
    get_thumbnail as media_get_thumbnail,
)
from backend.routers.photos_router import (
    delete_photo as photos_delete,
    list_photos as photos_list,
    upload_photos as photos_upload,
)
from backend.schemas.pydantic_models import (
    EventCreate,
    EventUpdate,
    GuestPinVerifyRequest,
    UserCreate,
    UserLogin,
)

class TestResponse:
    def __init__(self, status_code: int, data: Any = None, content: bytes = b"", headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self._data = data
        self.content = content if isinstance(content, bytes) else str(content).encode("utf-8")
        self.text = self.content.decode("utf-8", errors="replace")
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}

    def json(self):
        if self._data is not None:
            return self._data
        return json.loads(self.text)

class DummyRequest:
    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.headers = Headers(headers or {})
        self.base_url = "http://testserver/"

class EventFrameTestClient:
    """
    Direct synchronous test client that dispatches directly to FastAPI endpoints.
    Bypasses AnyIO 4.14 thread-portal blocking locks on Windows Python 3.14.
    Runs 100% in-memory, thread-safe, and deterministic (<1ms per request).
    """
    def __init__(self, db_session):
        self.db = db_session

    def _resolve_user(self, headers: Dict[str, str], query: Dict[str, str]) -> User:
        raw_token = None
        auth_hdr = headers.get("authorization") or headers.get("Authorization")
        if auth_hdr and auth_hdr.startswith("Bearer "):
            raw_token = auth_hdr[7:].strip()
        elif "token" in query:
            raw_token = query["token"]

        if not raw_token:
            raise HTTPException(status_code=401, detail="Authentication token required")
        payload = decode_access_token(raw_token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        user = self.db.query(User).filter(User.id == payload.get("sub"), User.is_active == True).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user

    def _resolve_guest_event(self, headers: Dict[str, str], query: Dict[str, str]) -> Event:
        token = query.get("token") or headers.get("x-guest-token") or headers.get("X-Guest-Token")
        if not token:
            raise HTTPException(status_code=401, detail="Guest access token required")
        event = self.db.query(Event).filter(Event.guest_token == token, Event.is_active == True).first()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found or revoked")
        return event

    def _format_result(self, res: Any, default_status: int = 200) -> TestResponse:
        if isinstance(res, FileResponse):
            with open(res.path, "rb") as f:
                content = f.read()
            hdrs = dict(res.headers)
            hdrs["content-type"] = res.media_type
            return TestResponse(status_code=res.status_code or default_status, content=content, headers=hdrs)
        elif isinstance(res, Response):
            content = res.body or b""
            hdrs = dict(res.headers)
            if res.media_type:
                hdrs["content-type"] = res.media_type
            return TestResponse(status_code=res.status_code or default_status, content=content, headers=hdrs)
        elif hasattr(res, "__table__"):
            d = {col.name: getattr(res, col.name) for col in res.__table__.columns}
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            for extra in ("photo_count", "face_count", "_confidence"):
                if hasattr(res, extra):
                    d[extra] = getattr(res, extra)
            return TestResponse(status_code=default_status, data=d, content=json.dumps(d).encode(), headers={"content-type": "application/json"})
        elif isinstance(res, BaseModel):
            data = res.model_dump(mode="json")
            return TestResponse(status_code=default_status, data=data, content=json.dumps(data).encode(), headers={"content-type": "application/json"})
        elif isinstance(res, list):
            data = []
            for item in res:
                if hasattr(item, "__table__"):
                    d = {col.name: getattr(item, col.name) for col in item.__table__.columns}
                    for k, v in d.items():
                        if hasattr(v, "isoformat"):
                            d[k] = v.isoformat()
                    for extra in ("photo_count", "face_count", "_confidence"):
                        if hasattr(item, extra):
                            d[extra] = getattr(item, extra)
                    data.append(d)
                elif isinstance(item, BaseModel):
                    data.append(item.model_dump(mode="json"))
                else:
                    data.append(item)
            return TestResponse(status_code=default_status, data=data, content=json.dumps(data).encode(), headers={"content-type": "application/json"})
        elif isinstance(res, dict):
            return TestResponse(status_code=default_status, data=res, content=json.dumps(res).encode(), headers={"content-type": "application/json"})
        return TestResponse(status_code=default_status)

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Any = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> TestResponse:
        parsed = urlparse(url)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        hdrs = headers or {}
        req = DummyRequest(url, hdrs)

        try:
            # 1. Auth routes
            if path == "/api/auth/register" and method == "POST":
                user_in = UserCreate(**(json_data or {}))
                res = auth_register(user_in, self.db)
                return self._format_result(res, default_status=201)

            if path == "/api/auth/login" and method == "POST":
                creds = UserLogin(**(json_data or {}))
                res = auth_login(creds, self.db)
                return self._format_result(res, default_status=200)

            if path == "/api/auth/me" and method == "GET":
                user = self._resolve_user(hdrs, query)
                res = auth_get_me(user)
                return self._format_result(res)

            # 2. Events routes
            if path == "/api/events" and method == "GET":
                user = self._resolve_user(hdrs, query)
                res = events_list(user, self.db)
                return self._format_result(res)

            if path == "/api/events" and method == "POST":
                user = self._resolve_user(hdrs, query)
                ev_in = EventCreate(**(json_data or {}))
                res = events_create(ev_in, user, self.db)
                return self._format_result(res, default_status=201)

            m = re.match(r"^/api/events/([^/]+)$", path)
            if m:
                ev_id = m.group(1)
                user = self._resolve_user(hdrs, query)
                if method == "GET":
                    res = events_get(ev_id, user, self.db)
                    return self._format_result(res)
                elif method == "PATCH":
                    ev_up = EventUpdate(**(json_data or {}))
                    res = events_update(ev_id, ev_up, user, self.db)
                    return self._format_result(res)
                elif method == "DELETE":
                    res = events_delete(ev_id, user, self.db)
                    return self._format_result(res, default_status=204)

            m = re.match(r"^/api/events/([^/]+)/regenerate-token$", path)
            if m and method == "POST":
                ev_id = m.group(1)
                user = self._resolve_user(hdrs, query)
                res = events_regenerate_token(ev_id, user, self.db)
                return self._format_result(res)

            m = re.match(r"^/api/events/network-info$", path)
            if m and method == "GET":
                user = self._resolve_user(hdrs, query)
                from backend.routers.events_router import get_network_info
                res = get_network_info(req, user)
                return self._format_result(res)

            m = re.match(r"^/api/events/([^/]+)/qr\.png$", path)
            if m and method == "GET":
                ev_id = m.group(1)
                user = self._resolve_user(hdrs, query)
                res = events_get_qr_png(ev_id, req, user, self.db, query.get("base_url"))
                return self._format_result(res)

            m = re.match(r"^/api/events/([^/]+)/qr\.svg$", path)
            if m and method == "GET":
                ev_id = m.group(1)
                user = self._resolve_user(hdrs, query)
                res = events_get_qr_svg(ev_id, req, user, self.db, query.get("base_url"))
                return self._format_result(res)

            m = re.match(r"^/api/events/([^/]+)/audit-logs$", path)
            if m and method == "GET":
                ev_id = m.group(1)
                user = self._resolve_user(hdrs, query)
                limit = int(query.get("limit", 50))
                res = events_get_audit_logs(ev_id, limit, user, self.db)
                return self._format_result(res)

            # 3. Photos routes
            m = re.match(r"^/api/events/([^/]+)/photos/upload$", path)
            if m and method == "POST":
                ev_id = m.group(1)
                user = self._resolve_user(hdrs, query)
                upload_files = []
                if files:
                    for field_name, file_tuple in files.items():
                        if isinstance(file_tuple, tuple):
                            fname, fbytes, ctype = file_tuple[0], file_tuple[1], file_tuple[2]
                        else:
                            fname, fbytes, ctype = "photo.jpg", file_tuple, "image/jpeg"
                        uf = UploadFile(filename=fname, file=io.BytesIO(fbytes), headers=Headers({"content-type": ctype}))
                        upload_files.append(uf)
                res = photos_upload(ev_id, upload_files, user, self.db)
                return self._format_result(res, default_status=201)

            m = re.match(r"^/api/events/([^/]+)/photos$", path)
            if m and method == "GET":
                ev_id = m.group(1)
                user = self._resolve_user(hdrs, query)
                page = int(query.get("page", 1))
                page_size = int(query.get("page_size", 24))
                res = photos_list(ev_id, page, page_size, user, self.db)
                return self._format_result(res)

            m = re.match(r"^/api/events/([^/]+)/photos/([^/]+)$", path)
            if m and method == "DELETE":
                ev_id, photo_id = m.group(1), m.group(2)
                user = self._resolve_user(hdrs, query)
                res = photos_delete(ev_id, photo_id, user, self.db)
                return self._format_result(res, default_status=204)

            # 4. Guest routes
            if path == "/api/guest/info" and method == "GET":
                ev = self._resolve_guest_event(hdrs, query)
                res = guest_get_info(ev)
                return self._format_result(res)

            if path == "/api/guest/verify-pin" and method == "POST":
                ev = self._resolve_guest_event(hdrs, query)
                req_data = GuestPinVerifyRequest(**(json_data or {}))
                res = guest_verify_pin(req_data, ev)
                return self._format_result(res)

            if path == "/api/guest/gallery" and method == "GET":
                ev = self._resolve_guest_event(hdrs, query)
                page = int(query.get("page", 1))
                page_size = int(query.get("page_size", 24))
                pin = query.get("pin")
                x_pin = hdrs.get("x-guest-pin") or hdrs.get("X-Guest-PIN")
                res = guest_get_gallery(page, page_size, pin, x_pin, ev, self.db)
                return self._format_result(res)

            if path == "/api/guest/selfie-search" and method == "POST":
                ev = self._resolve_guest_event(hdrs, query)
                consent = (data or {}).get("biometric_consent", "").lower() in ("true", "1")
                pin = (data or {}).get("pin")
                x_pin = hdrs.get("x-guest-pin") or hdrs.get("X-Guest-PIN")
                selfie_uf = None
                if files and "selfie" in files:
                    s_tuple = files["selfie"]
                    fname = s_tuple[0] if isinstance(s_tuple, tuple) else "selfie.jpg"
                    sbytes = s_tuple[1] if isinstance(s_tuple, tuple) else s_tuple
                    selfie_uf = UploadFile(filename=fname, file=io.BytesIO(sbytes))
                res = guest_search_selfie(selfie_uf, consent, pin, x_pin, ev, self.db)
                return self._format_result(res)

            # 5. Media delivery
            m = re.match(r"^/api/media/([^/]+)/thumbnail$", path)
            if m and method == "GET":
                photo_id = m.group(1)
                token = query.get("token")
                photo = verify_media_access(photo_id, req, token, self.db)
                res = media_get_thumbnail(photo)
                return self._format_result(res)

            m = re.match(r"^/api/media/([^/]+)/preview$", path)
            if m and method == "GET":
                photo_id = m.group(1)
                token = query.get("token")
                photo = verify_media_access(photo_id, req, token, self.db)
                res = media_get_preview(photo)
                return self._format_result(res)

            m = re.match(r"^/api/media/([^/]+)/original$", path)
            if m and method == "GET":
                photo_id = m.group(1)
                token = query.get("token")
                photo = verify_media_access(photo_id, req, token, self.db)
                res = media_get_original(photo)
                return self._format_result(res)

            return TestResponse(status_code=404, data={"detail": f"Path not found: {path}"})
        except HTTPException as exc:
            return TestResponse(status_code=exc.status_code, data={"detail": exc.detail})

    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> TestResponse:
        return self.request("GET", url, headers=headers)

    def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Any = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> TestResponse:
        return self.request("POST", url, headers=headers, json_data=json, data=data, files=files)

    def patch(self, url: str, headers: Optional[Dict[str, str]] = None, json: Any = None) -> TestResponse:
        return self.request("PATCH", url, headers=headers, json_data=json)

    def delete(self, url: str, headers: Optional[Dict[str, str]] = None) -> TestResponse:
        return self.request("DELETE", url, headers=headers)

@pytest.fixture(scope="session")
def test_temp_dir():
    temp_dir = Path(tempfile.mkdtemp(prefix="eventframe_test_"))
    yield temp_dir
    shutil.rmtree(str(temp_dir), ignore_errors=True)

@pytest.fixture(scope="function")
def db_session(test_temp_dir, monkeypatch):
    test_db_path = test_temp_dir / f"test_{os.urandom(4).hex()}.db"
    test_storage = test_temp_dir / f"storage_{os.urandom(4).hex()}"
    test_storage.mkdir(parents=True, exist_ok=True)
    (test_storage / "originals").mkdir(exist_ok=True)
    (test_storage / "previews").mkdir(exist_ok=True)
    (test_storage / "thumbnails").mkdir(exist_ok=True)

    monkeypatch.setattr(settings, "STORAGE_DIR", test_storage)
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{test_db_path}")

    engine = create_engine(f"sqlite:///{test_db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        if test_db_path.exists():
            try:
                test_db_path.unlink()
            except Exception:
                pass

@pytest.fixture(scope="function")
def client(db_session):
    return EventFrameTestClient(db_session)

@pytest.fixture(scope="function")
def test_user(db_session) -> User:
    user = User(
        email=f"photographer_{os.urandom(4).hex()}@eventframe.com",
        hashed_password=hash_password("password123"),
        full_name="Alex Rivera",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest.fixture(scope="function")
def auth_headers(test_user) -> dict:
    token = create_access_token({"sub": test_user.id, "email": test_user.email})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="function")
def test_event(db_session, test_user) -> Event:
    event = Event(
        owner_id=test_user.id,
        title="Gala Night 2026",
        slug=f"gala-{os.urandom(4).hex()}",
        venue="Metropolitan Hall",
        guest_token=f"token_{os.urandom(16).hex()}",
        pin_code=None,
        strict_selfie_mode=False,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event

def make_test_image(width: int = 400, height: int = 400, draw_face: bool = True) -> bytes:
    img = Image.new("RGB", (width, height), color=(220, 220, 220))
    draw = ImageDraw.Draw(img)

    if draw_face:
        cx, cy = width // 2, height // 2
        r = min(width, height) // 3
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(235, 195, 160), outline=(50, 50, 50), width=2)
        eye_r = r // 5
        draw.ellipse([cx - r//2 - eye_r, cy - r//3 - eye_r, cx - r//2 + eye_r, cy - r//3 + eye_r], fill=(30, 30, 30))
        draw.ellipse([cx + r//2 - eye_r, cy - r//3 - eye_r, cx + r//2 + eye_r, cy - r//3 + eye_r], fill=(30, 30, 30))
        draw.polygon([(cx, cy - r//6), (cx - r//8, cy + r//6), (cx + r//8, cy + r//6)], fill=(200, 150, 120))
        draw.arc([cx - r//3, cy, cx + r//3, cy + r//2], start=0, end=180, fill=(180, 50, 50), width=3)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()
