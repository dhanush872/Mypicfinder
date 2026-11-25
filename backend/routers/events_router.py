from datetime import datetime, timezone
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.auth.dependencies import get_current_user
from backend.auth.security import generate_guest_token
from backend.config import settings
from backend.models.database import get_db
from backend.models.entities import Event, FaceEmbedding, IngestionAuditLog, Photo, User
from backend.schemas.pydantic_models import (
    AuditLogResponse,
    EventCreate,
    EventResponse,
    EventUpdate,
    WatcherStatusResponse,
)
from backend.services.network_service import get_local_ip, get_network_info
from backend.services.qr_service import QRService
from backend.services.storage_service import StorageService
from backend.services.watcher_service import watcher_manager

router = APIRouter(prefix="/api/events", tags=["Events"])

@router.get("/system/network-info")
def get_sys_network_info(current_user: User = Depends(get_current_user)):
    """Return local Wi-Fi and public tunnel addresses for accurate QR code generation."""
    return get_network_info()

def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", slug)

def get_event_with_counts(event: Event, db: Session) -> EventResponse:
    photo_count = db.query(func.count(Photo.id)).filter(Photo.event_id == event.id).scalar() or 0
    face_count = db.query(func.count(FaceEmbedding.id)).filter(FaceEmbedding.event_id == event.id).scalar() or 0
    resp = EventResponse.model_validate(event)
    resp.photo_count = photo_count
    resp.face_count = face_count
    return resp

@router.get("", response_model=List[EventResponse])
def list_events(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List all events owned by the authenticated photographer."""
    events = (
        db.query(Event)
        .filter(Event.owner_id == current_user.id)
        .order_by(Event.created_at.desc())
        .all()
    )
    return [get_event_with_counts(ev, db) for ev in events]

@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    event_in: EventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new event with 256-bit unguessable guest token and optional PIN/strict mode."""
    base_slug = slugify(event_in.slug or event_in.title) or "event"
    slug = base_slug
    counter = 1
    while db.query(Event).filter(Event.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    guest_token = generate_guest_token()
    event_date = event_in.event_date or datetime.now(timezone.utc)

    event = Event(
        owner_id=current_user.id,
        title=event_in.title,
        slug=slug,
        venue=event_in.venue,
        event_date=event_date,
        guest_token=guest_token,
        pin_code=event_in.pin_code,
        strict_selfie_mode=event_in.strict_selfie_mode,
        watched_folder=event_in.watched_folder,
        watched_folder_active=event_in.watched_folder_active and bool(event_in.watched_folder),
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # Start watcher if requested
    if event.watched_folder_active and event.watched_folder:
        watcher_manager.start_watcher(event.id, event.watched_folder)

    return get_event_with_counts(event, db)

@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details for a specific event."""
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return get_event_with_counts(event, db)

@router.patch("/{event_id}", response_model=EventResponse)
def update_event(
    event_id: str,
    event_update: EventUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update event configuration, PIN, strict mode, or watched folder."""
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    data = event_update.model_dump(exclude_unset=True)
    for field, val in data.items():
        setattr(event, field, val)

    db.commit()
    db.refresh(event)

    # Update watcher state
    if event.watched_folder_active and event.watched_folder:
        watcher_manager.start_watcher(event.id, event.watched_folder)
    else:
        watcher_manager.stop_watcher(event.id)

    return get_event_with_counts(event, db)

@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    FULL CASCADE PURGE:
    1. Stop any running camera watched-folder workers.
    2. Permanently delete all photos, face embeddings, and audit logs from database.
    3. Purge all original, preview, and thumbnail files from filesystem.
    """
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # 1. Stop background watcher
    watcher_manager.stop_watcher(event.id)

    # 2. Database cascade delete
    db.delete(event)
    db.commit()

    # 3. Disk storage purge
    StorageService.purge_event_directory(event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/{event_id}/regenerate-token", response_model=EventResponse)
def regenerate_guest_token(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Kill-switch: instantly revokes previous guest link by issuing a new 256-bit token."""
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.guest_token = generate_guest_token()
    db.commit()
    db.refresh(event)
    return get_event_with_counts(event, db)

def _resolve_base_url(request: Request, override_url: Optional[str] = None) -> str:
    """Resolve base URL, converting localhost to local Wi-Fi IP so phones can connect."""
    if isinstance(override_url, str) and override_url.strip():
        return override_url.rstrip("/")
    if settings.PUBLIC_URL:
        return settings.PUBLIC_URL.rstrip("/")
    
    host = getattr(getattr(request, "url", None), "hostname", None) or "localhost"
    port = getattr(getattr(request, "url", None), "port", None) or settings.PORT
    scheme = getattr(getattr(request, "url", None), "scheme", None) or "http"
    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        local_ip = get_local_ip()
        return f"{scheme}://{local_ip}:{port}"
    return str(getattr(request, "base_url", "http://localhost:8000")).rstrip("/")

@router.get("/{event_id}/qr.png")
def get_qr_png(
    event_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    base_url: Optional[str] = Query(None)
):
    """Generate and return pixel-perfect PNG QR code for guest event sharing."""
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    resolved_base = _resolve_base_url(request, base_url)
    guest_url = f"{resolved_base}/guest?token={event.guest_token}"
    png_bytes = QRService.generate_png(guest_url)
    return Response(content=png_bytes, media_type="image/png")

@router.get("/{event_id}/qr.svg")
def get_qr_svg(
    event_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    base_url: Optional[str] = Query(None)
):
    """Generate and return crisp resolution-independent SVG QR code."""
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    resolved_base = _resolve_base_url(request, base_url)
    guest_url = f"{resolved_base}/guest?token={event.guest_token}"
    svg_str = QRService.generate_svg(guest_url)
    return Response(content=svg_str, media_type="image/svg+xml")

@router.get("/{event_id}/audit-logs", response_model=List[AuditLogResponse])
def get_audit_logs(
    event_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve recent photo ingestion audit logs for this event."""
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    logs = (
        db.query(IngestionAuditLog)
        .filter(IngestionAuditLog.event_id == event_id)
        .order_by(IngestionAuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return logs

@router.get("/{event_id}/watcher-status", response_model=WatcherStatusResponse)
def get_watcher_status(
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get active live camera tethering watched folder status."""
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    status_data = watcher_manager.get_status(event_id)
    return WatcherStatusResponse(
        event_id=event_id,
        watched_folder=event.watched_folder,
        is_active=status_data.get("is_active", False),
        last_scanned_at=status_data.get("last_scanned_at"),
        files_processed=status_data.get("files_processed", 0),
        errors=status_data.get("errors", 0),
    )

@router.post("/{event_id}/watcher-toggle", response_model=WatcherStatusResponse)
def toggle_watcher(
    event_id: str,
    active: bool = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start or stop automated live camera tethering watcher."""
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not event.watched_folder and active:
        raise HTTPException(status_code=400, detail="Watched folder path is not configured for this event")

    event.watched_folder_active = active
    db.commit()

    if active and event.watched_folder:
        watcher_manager.start_watcher(event_id, event.watched_folder)
    else:
        watcher_manager.stop_watcher(event_id)

    status_data = watcher_manager.get_status(event_id)
    return WatcherStatusResponse(
        event_id=event_id,
        watched_folder=event.watched_folder,
        is_active=status_data.get("is_active", False),
        last_scanned_at=status_data.get("last_scanned_at"),
        files_processed=status_data.get("files_processed", 0),
        errors=status_data.get("errors", 0),
    )
