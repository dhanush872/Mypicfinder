from backend.routers.auth_router import router as auth_router
from backend.routers.events_router import router as events_router
from backend.routers.guest_router import router as guest_router
from backend.routers.media_router import router as media_router
from backend.routers.photos_router import router as photos_router

__all__ = ["auth_router", "events_router", "photos_router", "guest_router", "media_router"]
