import os
from pathlib import Path
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="allow")

    APP_NAME: str = "EventFrame"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "eventframe-insecure-default-change-in-prod-7f8d9a2b1c3e4f5a6b7c8d9e")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./eventframe.db")
    
    # Storage
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    STORAGE_DIR: Path = Path(os.getenv("STORAGE_DIR", str(Path(__file__).resolve().parent.parent / "storage")))
    
    # Face Matcher Engine
    FACE_MATCHER_BACKEND: str = os.getenv("FACE_MATCHER_BACKEND", "auto")  # "auto", "deep", or "local"
    FACE_SIMILARITY_THRESHOLD: float = float(os.getenv("FACE_SIMILARITY_THRESHOLD", "0.55"))
    MODELS_DIR: Path = Path(__file__).resolve().parent.parent / "models"
    
    # Ingestion & Camera Tethering
    WATCHER_POLL_INTERVAL: float = float(os.getenv("WATCHER_POLL_INTERVAL", "2.0"))
    FILE_STABILIZATION_DELAY: float = float(os.getenv("FILE_STABILIZATION_DELAY", "0.5"))
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
    
    # Server / Host
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    PUBLIC_URL: str = os.getenv("PUBLIC_URL", "")

settings = Settings()
# Ensure critical directories exist
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
(settings.STORAGE_DIR / "originals").mkdir(parents=True, exist_ok=True)
(settings.STORAGE_DIR / "previews").mkdir(parents=True, exist_ok=True)
(settings.STORAGE_DIR / "thumbnails").mkdir(parents=True, exist_ok=True)
settings.MODELS_DIR.mkdir(parents=True, exist_ok=True)
