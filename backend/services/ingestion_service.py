from datetime import datetime, timezone
import hashlib
import io
import os
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageOps
from PIL.ExifTags import TAGS
from sqlalchemy.orm import Session
from backend.models.entities import Event, FaceEmbedding, IngestionAuditLog, Photo
from backend.services.face_service import FaceService
from backend.services.storage_service import StorageService

def parse_exif_datetime(dt_str: str) -> Optional[datetime]:
    """Parse EXIF timestamp formats like '2026:11:24 14:30:00'."""
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            dt = datetime.strptime(dt_str.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None

class IngestionService:
    @staticmethod
    def extract_metadata(pil_img: Image.Image) -> dict:
        """Extract capture timestamp, camera make, model, lens from EXIF."""
        meta = {
            "captured_at": None,
            "camera_make": None,
            "camera_model": None,
            "lens_model": None,
        }
        try:
            exif_data = pil_img.getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, tag_id)
                    if tag_name == "DateTimeOriginal" or tag_name == "DateTime":
                        if isinstance(value, str):
                            meta["captured_at"] = parse_exif_datetime(value)
                    elif tag_name == "Make" and isinstance(value, str):
                        meta["camera_make"] = value.strip()
                    elif tag_name == "Model" and isinstance(value, str):
                        meta["camera_model"] = value.strip()
                    elif tag_name == "LensModel" and isinstance(value, str):
                        meta["lens_model"] = value.strip()
        except Exception:
            pass
        return meta

    @classmethod
    def ingest_photo_bytes(
        cls,
        event_id: str,
        filename: str,
        file_bytes: bytes,
        db: Session,
        source: str = "upload"
    ) -> Tuple[Optional[Photo], str]:
        """
        Process and ingest raw photo bytes:
        1. Compute SHA-256 content hash for deduplication.
        2. Normalize EXIF orientation in RAM.
        3. Extract metadata and parallel derivatives (400px thumb, 1600px preview).
        4. Detect faces and generate normalized vector embeddings.
        5. Persist Photo, FaceEmbedding, and AuditLog records.
        """
        if not file_bytes or len(file_bytes) == 0:
            cls._log_audit(db, event_id, source, filename, "error", "Empty file payload")
            return None, "Empty file"

        # 1. SHA-256 Content Deduplication
        content_hash = hashlib.sha256(file_bytes).hexdigest()
        
        # Check if identical photo already exists in this event
        existing = db.query(Photo).filter(
            Photo.event_id == event_id,
            Photo.content_hash == content_hash
        ).first()
        
        if existing:
            cls._log_audit(db, event_id, source, filename, "duplicate", f"Skipped duplicate SHA-256 {content_hash[:8]}")
            return existing, "duplicate"

        # 2. Decode and normalize in memory
        try:
            with Image.open(io.BytesIO(file_bytes)) as raw_img:
                metadata = cls.extract_metadata(raw_img)
                # Correct EXIF orientation transpose
                normalized_img = ImageOps.exif_transpose(raw_img)
                if normalized_img.mode != "RGB":
                    normalized_img = normalized_img.convert("RGB")
                    
                width, height = normalized_img.size
                
                # 3. Store original and generate derivatives
                ext = Path(filename).suffix.lstrip(".") or "jpg"
                orig_rel, _ = StorageService.save_original(event_id, content_hash, ext, file_bytes)
                prev_rel, thumb_rel = StorageService.generate_and_save_derivatives(event_id, content_hash, normalized_img)
                
                # 4. Extract Face Embeddings
                face_descriptors = FaceService.extract_faces_from_image(normalized_img)
        except Exception as e:
            cls._log_audit(db, event_id, source, filename, "error", f"Image processing failed: {str(e)}")
            return None, f"Image processing failed: {str(e)}"

        # 5. Database persistence inside transaction
        photo = Photo(
            event_id=event_id,
            filename=filename,
            content_hash=content_hash,
            file_path=orig_rel,
            preview_path=prev_rel,
            thumbnail_path=thumb_rel,
            file_size=len(file_bytes),
            width=width,
            height=height,
            captured_at=metadata["captured_at"],
            camera_make=metadata["camera_make"],
            camera_model=metadata["camera_model"],
            lens_model=metadata["lens_model"],
            ingestion_source=source,
        )
        db.add(photo)
        db.flush()  # obtain photo.id

        for f_desc in face_descriptors:
            face_emb = FaceEmbedding(
                photo_id=photo.id,
                event_id=event_id,
                bbox_x=f_desc.bbox[0],
                bbox_y=f_desc.bbox[1],
                bbox_w=f_desc.bbox[2],
                bbox_h=f_desc.bbox[3],
                confidence=f_desc.confidence,
                embedding=f_desc.embedding.astype("float32").tobytes(),
                dimension=len(f_desc.embedding),
            )
            db.add(face_emb)

        cls._log_audit(db, event_id, source, filename, "success", f"Ingested ({width}x{height}, {len(face_descriptors)} faces)")
        db.commit()
        db.refresh(photo)
        return photo, "success"

    @classmethod
    def ingest_photo_file(
        cls,
        event_id: str,
        file_path: Path,
        db: Session,
        source: str = "watched_folder"
    ) -> Tuple[Optional[Photo], str]:
        """Ingest a photo file from local disk."""
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            return cls.ingest_photo_bytes(event_id, file_path.name, data, db, source=source)
        except Exception as e:
            cls._log_audit(db, event_id, source, file_path.name, "error", f"File read failed: {str(e)}")
            return None, str(e)

    @staticmethod
    def _log_audit(db: Session, event_id: str, source: str, filename: str, status_code: str, message: str):
        try:
            log_entry = IngestionAuditLog(
                event_id=event_id,
                source=source,
                filename=filename,
                status=status_code,
                message=message,
            )
            db.add(log_entry)
            db.commit()
        except Exception:
            db.rollback()
