from math import ceil
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from backend.auth.dependencies import get_guest_event
from backend.models.database import get_db
from backend.models.entities import Event, Photo
from backend.schemas.pydantic_models import (
    FaceSearchResponse,
    GuestEventInfo,
    GuestPinVerifyRequest,
    PaginatedPhotos,
    PhotoResponse,
)
from backend.services.face_service import FaceService

router = APIRouter(prefix="/api/guest", tags=["Guest Portal"])

def verify_optional_pin(event: Event, request_pin: Optional[str]):
    """If event has a 4-digit PIN configured, ensure it is provided and correct."""
    if event.pin_code:
        if not request_pin or request_pin != event.pin_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="PIN code required for this event",
            )

@router.get("/info", response_model=GuestEventInfo)
def get_guest_event_info(event: Event = Depends(get_guest_event)):
    """
    Get public guest event details. Never exposes photographer credentials,
    internal filesystem paths, or other events.
    """
    return GuestEventInfo(
        id=event.id,
        title=event.title,
        slug=event.slug,
        venue=event.venue,
        event_date=event.event_date,
        strict_selfie_mode=event.strict_selfie_mode,
        has_pin=bool(event.pin_code),
    )

@router.post("/verify-pin")
def verify_pin(
    pin_req: GuestPinVerifyRequest,
    event: Event = Depends(get_guest_event)
):
    """Verify 4-digit PIN code for protected events."""
    if not event.pin_code:
        return {"verified": True, "message": "No PIN required"}
        
    if pin_req.pin_code != event.pin_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect 4-digit PIN code",
        )
    return {"verified": True, "message": "PIN verified successfully"}

@router.get("/gallery", response_model=PaginatedPhotos)
def get_guest_gallery(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    pin: Optional[str] = Query(None),
    x_guest_pin: Optional[str] = Header(None, alias="X-Guest-PIN"),
    event: Event = Depends(get_guest_event),
    db: Session = Depends(get_db)
):
    """
    Chronological paginated browsing for guests.
    CRITICAL: Blocked if the event has Strict Selfie-Only Mode enabled!
    """
    effective_pin = pin or x_guest_pin
    verify_optional_pin(event, effective_pin)

    # Enforce Strict Selfie-Only Mode
    if event.strict_selfie_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Strict selfie-only mode is enabled for this event. Public browsing is disabled; find your photos by taking a selfie.",
        )

    query = db.query(Photo).filter(Photo.event_id == event.id)
    total = query.count()
    total_pages = ceil(total / page_size) if total > 0 else 1

    photos = (
        query.order_by(Photo.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [PhotoResponse.model_validate(p) for p in photos]
    return PaginatedPhotos(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@router.post("/selfie-search", response_model=FaceSearchResponse)
def search_photos_by_selfie(
    selfie: UploadFile = File(...),
    biometric_consent: bool = Form(...),
    pin: Optional[str] = Form(None),
    x_guest_pin: Optional[str] = Header(None, alias="X-Guest-PIN"),
    event: Event = Depends(get_guest_event),
    db: Session = Depends(get_db)
):
    """
    Search event photos matching a guest's selfie.
    PRIVACY GUARANTEES:
    - Biometric consent checkbox is strictly required.
    - Selfie is processed STRICTLY in volatile RAM (never written to disk or database).
    - Event-scoped: vector query is locked to current event.
    """
    effective_pin = pin or x_guest_pin
    verify_optional_pin(event, effective_pin)

    if hasattr(selfie, "file") and selfie.file:
        selfie_bytes = selfie.file.read()
    else:
        selfie_bytes = b""
    return FaceService.search_by_selfie(
        event_id=event.id,
        selfie_bytes=selfie_bytes,
        biometric_consent=biometric_consent,
        db=db
    )
