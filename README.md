# EventFrame: Local-First Event Photo Delivery Platform

EventFrame is a modular monolith bridging physical camera tethering at live events with instant, privacy-first guest photo delivery.

## Architecture & Technology Stack
- **Backend**: Python 3.12+ with FastAPI, SQLAlchemy 2.0 (SQLite WAL mode locally, PostgreSQL + pgvector ready), Pillow, NumPy, ONNX Runtime.
- **Frontend**: Vanilla HTML5, CSS3, ES6+ Progressive Web App (PWA) with client-side downscaling and service worker.
- **Biometric Engine**:
  - `LocalFeatureFaceMatcher`: 100% offline spatial HOG + LBP + Color descriptor (zero external binary dependencies).
  - `DeepFaceMatcher`: SCRFD face detection + ArcFace 512-dim normalized embeddings via ONNX Runtime.
  - Cosine distance matrix multiplication in <5ms.
- **Privacy Architecture**:
  - Mandatory biometric consent.
  - Guest selfies processed **strictly in volatile RAM** (never written to disk, database, or server logs).
  - Strict event isolation (`WHERE event_id = current_event_id`).
  - Full cascade purge on event or photo deletion.

---

## Quick Start Guide

### 1. Initialize Photographer Admin Account
```bash
python scripts/create_photographer.py --email admin@eventframe.local --password secret123 --name "Lead Photographer"
```

### 2. Launch Local-First Server
```bash
python scripts/run_server.py
```
- Photographer Dashboard: `http://localhost:8000/`
- Local Venue Wi-Fi Access: `http://<YOUR_LOCAL_IP>:8000/`

---

## Live Camera Tethering (Watched Folder)
Compatible with:
- **Sony Imaging Edge** (Remote)
- **Canon EOS Utility**
- **Nikon NX Tether**
- **Adobe Lightroom Classic** (Tethered Capture)

### How It Works:
1. Configure your tethering software to save captured photos into a folder on your laptop (e.g. `C:\Tethered\Event2026`).
2. In the EventFrame Photographer Dashboard, paste this folder path under **Camera Tethering Watched Folder** in the event settings.
3. Click **Start Auto-Ingestion**.
4. EventFrame's background worker continuously scans the folder:
   - Performs **file-size stabilization probing** and **read-lock verification** so incomplete/writing files are never ingested prematurely.
   - Extracts EXIF timestamps, camera make/model, and corrects orientation.
   - Generates 400px thumbnails and 1600px previews.
   - Indexes face embeddings in the event vector store.
   - Appends detailed records to the **Ingestion Audit Log**.

---

## Public HTTPS Tunneling (Cloudflare Tunnel)
If external guests or venue attendees without local Wi-Fi need access:
1. Install [Cloudflare `cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/).
2. Run the quick tunnel command:
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```
3. Copy the generated `https://*.trycloudflare.com` URL into your browser or set `PUBLIC_URL` in `.env`.

---

## Verification & Packaging
Run all unit and integration tests and build the distributable zip:
```bash
python scripts/run_checks.py
```
