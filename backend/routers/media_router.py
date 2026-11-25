from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from backend.auth.dependencies import verify_media_access
from backend.models.entities import Photo
from backend.services.storage_service import StorageService

router = APIRouter(prefix="/api/media", tags=["Media Delivery"])

@router.get("/{photo_id}/thumbnail")
def get_thumbnail(photo: Photo = Depends(verify_media_access)):
    """Serve 400px optimized thumbnail with token validation."""
    abs_path = StorageService.resolve_photo_path(photo.thumbnail_path)
    if not abs_path or not abs_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(
        path=str(abs_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400, immutable"},
    )

@router.get("/{photo_id}/preview")
def get_preview(photo: Photo = Depends(verify_media_access)):
    """Serve 1600px preview with token validation."""
    abs_path = StorageService.resolve_photo_path(photo.preview_path)
    if not abs_path or not abs_path.exists():
        raise HTTPException(status_code=404, detail="Preview not found")

    return FileResponse(
        path=str(abs_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400, immutable"},
    )

@router.get("/{photo_id}/original")
def get_original(photo: Photo = Depends(verify_media_access)):
    """Download full-resolution original photo with token validation."""
    abs_path = StorageService.resolve_photo_path(photo.file_path)
    if not abs_path or not abs_path.exists():
        raise HTTPException(status_code=404, detail="Original photo file not found")

    media_type = "image/jpeg"
    ext = abs_path.suffix.lower()
    if ext in (".png",):
        media_type = "image/png"
    elif ext in (".webp",):
        media_type = "image/webp"

    return FileResponse(
        path=str(abs_path),
        media_type=media_type,
        filename=photo.filename,
        headers={
            "Content-Disposition": f'attachment; filename="{photo.filename}"',
            "Cache-Control": "private, max-age=86400, immutable",
        },
    )
