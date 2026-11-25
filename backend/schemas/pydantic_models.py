from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr, Field

# --- User & Auth Schemas ---
class UserBase(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str = "Photographer"

class UserCreate(UserBase):
    password: str = Field(min_length=4)

class UserLogin(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str

class UserResponse(UserBase):
    id: str
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# --- Event Schemas ---
class EventBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    slug: Optional[str] = None
    venue: Optional[str] = None
    event_date: Optional[datetime] = None
    pin_code: Optional[str] = Field(None, max_length=4, pattern=r"^\d{4}$")
    strict_selfie_mode: bool = False
    watched_folder: Optional[str] = None
    watched_folder_active: bool = False

class EventCreate(EventBase):
    pass

class EventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    venue: Optional[str] = None
    event_date: Optional[datetime] = None
    pin_code: Optional[str] = Field(None, max_length=4, pattern=r"^\d{4}$")
    strict_selfie_mode: Optional[bool] = None
    is_active: Optional[bool] = None
    watched_folder: Optional[str] = None
    watched_folder_active: Optional[bool] = None

class EventResponse(BaseModel):
    id: str
    owner_id: str
    title: str
    slug: str
    venue: Optional[str] = None
    event_date: datetime
    guest_token: str
    pin_code: Optional[str] = None
    strict_selfie_mode: bool
    is_active: bool
    watched_folder: Optional[str] = None
    watched_folder_active: bool
    created_at: datetime
    updated_at: datetime
    photo_count: int = 0
    face_count: int = 0
    model_config = ConfigDict(from_attributes=True)

class GuestEventInfo(BaseModel):
    """Guest-safe event information that never leaks owner details or internal paths."""
    id: str
    title: str
    slug: str
    venue: Optional[str] = None
    event_date: datetime
    strict_selfie_mode: bool
    has_pin: bool
    model_config = ConfigDict(from_attributes=True)

class GuestPinVerifyRequest(BaseModel):
    pin_code: str = Field(pattern=r"^\d{4}$")

# --- Photo Schemas ---
class PhotoResponse(BaseModel):
    id: str
    event_id: str
    filename: str
    file_size: int
    width: int
    height: int
    captured_at: Optional[datetime] = None
    camera_make: Optional[Optional[str]] = None
    camera_model: Optional[Optional[str]] = None
    ingestion_source: str
    created_at: datetime
    face_count: int = 0
    model_config = ConfigDict(from_attributes=True)

class PaginatedPhotos(BaseModel):
    items: List[PhotoResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

# --- Face Match Schemas ---
class FaceMatchResult(BaseModel):
    photo: PhotoResponse
    confidence: float
    bbox: List[float]  # [x, y, w, h] normalized 0..1

class FaceSearchResponse(BaseModel):
    query_faces_detected: int
    match_count: int
    matches: List[FaceMatchResult]
    latency_ms: float

# --- Audit & System Schemas ---
class AuditLogResponse(BaseModel):
    id: int
    event_id: str
    source: str
    filename: str
    status: str
    message: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class WatcherStatusResponse(BaseModel):
    event_id: str
    watched_folder: Optional[str]
    is_active: bool
    last_scanned_at: Optional[datetime] = None
    files_processed: int = 0
    errors: int = 0
