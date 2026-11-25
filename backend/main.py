from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.config import settings
from backend.models.database import init_db
from backend.routers import auth_router, events_router, guest_router, media_router, photos_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup
    init_db()
    yield
    # Shutdown watchers on exit
    from backend.services.watcher_service import watcher_manager
    for event_id in list(watcher_manager._workers.keys()):
        watcher_manager.stop_watcher(event_id)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Local-First Event Photo Delivery Platform bridging camera tethering with instant privacy-first guest delivery.",
    lifespan=lifespan,
)

# Enable CORS for local-first venue Wi-Fi and Cloudflare Tunneling
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(auth_router)
app.include_router(events_router)
app.include_router(photos_router)
app.include_router(guest_router)
app.include_router(media_router)

# Mount Frontend Static Directories
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
css_dir = frontend_dir / "css"
js_dir = frontend_dir / "js"

css_dir.mkdir(parents=True, exist_ok=True)
js_dir.mkdir(parents=True, exist_ok=True)

app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")

@app.get("/")
def serve_dashboard():
    """Serve Photographer Admin Dashboard."""
    index_file = frontend_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file), media_type="text/html")
    return {"message": "EventFrame API is running. Frontend index.html not yet installed."}

@app.get("/guest")
def serve_guest_portal():
    """Serve Guest Mobile-First PWA Portal."""
    guest_file = frontend_dir / "guest.html"
    if guest_file.exists():
        return FileResponse(str(guest_file), media_type="text/html")
    return {"message": "EventFrame Guest Portal."}

@app.get("/manifest.json")
def serve_manifest():
    manifest_file = frontend_dir / "manifest.json"
    if manifest_file.exists():
        return FileResponse(str(manifest_file), media_type="application/manifest+json")
    return {}

@app.get("/sw.js")
def serve_service_worker():
    sw_file = frontend_dir / "sw.js"
    if sw_file.exists():
        return FileResponse(str(sw_file), media_type="application/javascript")
    return Response(content="// sw", media_type="application/javascript")
