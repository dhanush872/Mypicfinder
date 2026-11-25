import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from backend.models.database import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False, default="Photographer")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    events = relationship("Event", back_populates="owner", cascade="all, delete-orphan")

class Event(Base):
    __tablename__ = "events"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    venue = Column(String(255), nullable=True)
    event_date = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    # Guest access configuration
    guest_token = Column(String(64), unique=True, index=True, nullable=False)
    pin_code = Column(String(4), nullable=True)  # Optional 4-digit PIN
    strict_selfie_mode = Column(Boolean, default=False, nullable=False)  # Disables public gallery
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Camera tethering watched folder
    watched_folder = Column(Text, nullable=True)
    watched_folder_active = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    
    owner = relationship("User", back_populates="events")
    photos = relationship("Photo", back_populates="event", cascade="all, delete-orphan")
    audit_logs = relationship("IngestionAuditLog", back_populates="event", cascade="all, delete-orphan")

class Photo(Base):
    __tablename__ = "photos"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)  # SHA-256 for dedup
    
    # Relative storage paths from STORAGE_DIR
    file_path = Column(String(512), nullable=False)       # originals/
    preview_path = Column(String(512), nullable=False)    # previews/ (1600px)
    thumbnail_path = Column(String(512), nullable=False)  # thumbnails/ (400px)
    
    file_size = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    
    # EXIF metadata
    captured_at = Column(DateTime(timezone=True), nullable=True)
    camera_make = Column(String(128), nullable=True)
    camera_model = Column(String(128), nullable=True)
    lens_model = Column(String(128), nullable=True)
    
    ingestion_source = Column(String(32), default="upload", nullable=False)  # "upload" or "watched_folder"
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    
    event = relationship("Event", back_populates="photos")
    faces = relationship("FaceEmbedding", back_populates="photo", cascade="all, delete-orphan")

class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    photo_id = Column(String(36), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True)
    # Event ID is denormalized to ensure strict event-isolated vector queries
    event_id = Column(String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Bounding box relative to image (0.0 to 1.0)
    bbox_x = Column(Float, nullable=False)
    bbox_y = Column(Float, nullable=False)
    bbox_w = Column(Float, nullable=False)
    bbox_h = Column(Float, nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)
    
    # Vector embedding stored as raw IEEE 754 float32 bytes for zero-copy high speed numpy reconstruction
    embedding = Column(LargeBinary, nullable=False)
    dimension = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    photo = relationship("Photo", back_populates="faces")

class IngestionAuditLog(Base):
    __tablename__ = "ingestion_audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(32), nullable=False)  # "upload" | "watched_folder"
    filename = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False)  # "success" | "duplicate" | "error" | "skipped"
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    event = relationship("Event", back_populates="audit_logs")
