from math import ceil
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.auth.dependencies import get_current_user
from backend.models.database import get_db
from backend.models.entities import Event, FaceEmbedding, Photo, User
from backend.schemas.pydantic_models import PaginatedPhotos, PhotoResponse
from backend.services.ingestion_service import IngestionService
from backend.services.storage_service import StorageService

router = APIRouter(prefix="/api/events/{event_id}/photos", tags=["Photos"])

@router.post("/upload", response_model=List[PhotoResponse], status_code=status.HTTP_201_CREATED)
def upload_photos(
    event_id: str,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Bulk manual drag-and-drop web upload with streaming hash computation
    and SHA-256 content deduplication.
    """
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    results: List[PhotoResponse] = []
    for upload in files:
        # Read stream synchronously
        if hasattr(upload, "file") and upload.file:
            file_bytes = upload.file.read()
        else:
            file_bytes = b""
        if not file_bytes:
            continue

        photo, status_code = IngestionService.ingest_photo_bytes(
            event_id=event.id,
            filename=upload.filename or "upload.jpg",
            file_bytes=file_bytes,
            db=db,
            source="upload"
        )

        if photo:
            resp = PhotoResponse.model_validate(photo)
            resp.face_count = db.query(func.count(FaceEmbedding.id)).filter(FaceEmbedding.photo_id == photo.id).scalar() or 0
            results.append(resp)

    return results

@router.get("", response_model=PaginatedPhotos)
def list_photos(
    event_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List photos in an event, chronologically paginated with face counts."""
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    query = db.query(Photo).filter(Photo.event_id == event_id)
    total = query.count()
    total_pages = ceil(total / page_size) if total > 0 else 1

    photos = (
        query.order_by(Photo.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for p in photos:
        resp = PhotoResponse.model_validate(p)
        resp.face_count = len(p.faces)
        items.append(resp)

    return PaginatedPhotos(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@router.delete("/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(
    event_id: str,
    photo_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a photo with full cascade purge:
    Removes photo entity, all associated face embeddings, and all files from disk.
    """
    event = db.query(Event).filter(Event.id == event_id, Event.owner_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    photo = db.query(Photo).filter(Photo.id == photo_id, Photo.event_id == event_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Capture storage paths before DB deletion
    file_path = photo.file_path
    preview_path = photo.preview_path
    thumbnail_path = photo.thumbnail_path

    # Delete from DB (Face embeddings deleted via database cascade)
    db.delete(photo)
    db.commit()

    # Purge files from disk
    StorageService.purge_photo_files(file_path, preview_path, thumbnail_path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
