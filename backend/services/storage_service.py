import os
from pathlib import Path
import shutil
from typing import Optional, Tuple
from PIL import Image, ImageOps
from backend.config import settings

class StorageService:
    @staticmethod
    def sanitize_path(base_dir: Path, relative_path: str) -> Path:
        """
        Clean path-traversal sanitization:
        Resolves the absolute target path and strictly verifies it resides within base_dir.
        """
        # Strip leading slashes to prevent root escapes
        clean_rel = relative_path.lstrip("/\\")
        target = (base_dir / clean_rel).resolve()
        base = base_dir.resolve()
        
        if base != target and base not in target.parents:
            raise ValueError(f"Path traversal detected: {relative_path}")
        return target

    @classmethod
    def get_event_dir(cls, category: str, event_id: str) -> Path:
        """Get or create directory for event in originals, previews, or thumbnails."""
        base_cat = settings.STORAGE_DIR / category
        event_dir = cls.sanitize_path(base_cat, event_id)
        event_dir.mkdir(parents=True, exist_ok=True)
        return event_dir

    @classmethod
    def save_original(cls, event_id: str, content_hash: str, ext: str, file_bytes: bytes) -> Tuple[str, Path]:
        """Save original raw image to storage/originals/<event_id>/<content_hash>.<ext>."""
        clean_ext = ext.lstrip(".").lower()
        if not clean_ext:
            clean_ext = "jpg"
            
        event_dir = cls.get_event_dir("originals", event_id)
        filename = f"{content_hash}.{clean_ext}"
        target_path = event_dir / filename
        
        with open(target_path, "wb") as f:
            f.write(file_bytes)
            
        rel_path = f"originals/{event_id}/{filename}"
        return rel_path, target_path

    @classmethod
    def generate_and_save_derivatives(
        cls,
        event_id: str,
        content_hash: str,
        normalized_image: Image.Image
    ) -> Tuple[str, str]:
        """
        Generate 1600px web preview and 400px thumbnail with high-quality resampling.
        Saves as optimized progressive JPEGs.
        Returns (preview_rel_path, thumbnail_rel_path).
        """
        preview_dir = cls.get_event_dir("previews", event_id)
        thumb_dir = cls.get_event_dir("thumbnails", event_id)
        
        preview_filename = f"{content_hash}.jpg"
        thumb_filename = f"{content_hash}.jpg"
        
        preview_path = preview_dir / preview_filename
        thumb_path = thumb_dir / thumb_filename
        
        # 1. 1600px Preview
        preview_img = normalized_image.copy()
        preview_img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        if preview_img.mode != "RGB":
            preview_img = preview_img.convert("RGB")
        preview_img.save(str(preview_path), "JPEG", quality=88, progressive=True, optimize=True)
        
        # 2. 400px Thumbnail
        thumb_img = normalized_image.copy()
        thumb_img.thumbnail((400, 400), Image.Resampling.LANCZOS)
        if thumb_img.mode != "RGB":
            thumb_img = thumb_img.convert("RGB")
        thumb_img.save(str(thumb_path), "JPEG", quality=85, optimize=True)
        
        return f"previews/{event_id}/{preview_filename}", f"thumbnails/{event_id}/{thumb_filename}"

    @classmethod
    def resolve_photo_path(cls, rel_path: str) -> Optional[Path]:
        """Safely resolve relative storage path to absolute filesystem path."""
        try:
            target = cls.sanitize_path(settings.STORAGE_DIR, rel_path)
            if target.exists() and target.is_file():
                return target
            return None
        except ValueError:
            return None

    @classmethod
    def purge_photo_files(cls, file_path: str, preview_path: str, thumbnail_path: str):
        """Purge all derivative and original files of a photo from disk."""
        for p in (file_path, preview_path, thumbnail_path):
            if p:
                try:
                    full_path = cls.resolve_photo_path(p)
                    if full_path and full_path.exists():
                        full_path.unlink()
                except Exception:
                    pass

    @classmethod
    def purge_event_directory(cls, event_id: str):
        """Full cascade purge: completely delete all storage directories for an event."""
        for cat in ("originals", "previews", "thumbnails"):
            try:
                event_dir = settings.STORAGE_DIR / cat / event_id
                target = cls.sanitize_path(settings.STORAGE_DIR / cat, event_id)
                if target.exists() and target.is_dir():
                    shutil.rmtree(str(target), ignore_errors=True)
            except Exception:
                pass
