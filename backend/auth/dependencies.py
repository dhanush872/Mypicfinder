from typing import Optional
from fastapi import Depends, HTTPException, Query, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from backend.auth.security import decode_access_token
from backend.models.database import get_db
from backend.models.entities import Event, Photo, User

# We use auto_error=False on HTTPBearer so we can fall back to ?token= query parameter for media tags
security_bearer = HTTPBearer(auto_error=False)

def get_token_from_request(
    request: Request,
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    token_query: Optional[str] = Query(None, alias="token"),
) -> Optional[str]:
    """
    Extract token from Authorization: Bearer header OR ?token= query parameter.
    Enables native HTML <img src="/api/media/.../?token=..."> loading without custom headers.
    """
    if auth and auth.credentials:
        return auth.credentials
    if token_query:
        return token_query
    # Check X-Guest-Token header
    guest_header = request.headers.get("X-Guest-Token")
    if guest_header:
        return guest_header
    return None

def get_current_user(
    request: Request,
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    token_query: Optional[str] = Query(None, alias="token"),
    db: Session = Depends(get_db),
) -> User:
    """Dependency that authenticates a photographer user via JWT."""
    raw_token = None
    if auth and auth.credentials:
        raw_token = auth.credentials
    elif token_query:
        raw_token = token_query
        
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    payload = decode_access_token(raw_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload",
        )
        
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
        
    return user

def get_guest_event(
    request: Request,
    token: Optional[str] = Query(None, alias="token"),
    db: Session = Depends(get_db),
) -> Event:
    """
    Dependency that resolves the active Event from the guest unguessable token.
    Token can be passed via ?token=<guest_token> or X-Guest-Token header.
    """
    raw_token = token or request.headers.get("X-Guest-Token")
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Guest access token required",
        )
        
    event = db.query(Event).filter(Event.guest_token == raw_token, Event.is_active == True).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found or guest access has been revoked",
        )
        
    return event

def verify_media_access(
    photo_id: str,
    request: Request,
    token: Optional[str] = Query(None, alias="token"),
    db: Session = Depends(get_db),
) -> Photo:
    """
    Protected media access validator:
    Permits access if the requester presents:
    1) Valid photographer JWT token (user owns the event containing the photo)
    2) Valid guest token for the photo's event
    Never exposes raw filesystem media without validation.
    """
    raw_token = token
    if not raw_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()
        else:
            raw_token = request.headers.get("X-Guest-Token")
            
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token required for media delivery",
        )
        
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
        
    event = db.query(Event).filter(Event.id == photo.event_id).first()
    if not event or not event.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event unavailable")
        
    # Check 1: Is this raw_token the event's guest token?
    if raw_token == event.guest_token:
        return photo
        
    # Check 2: Is this raw_token a valid JWT for the event owner?
    payload = decode_access_token(raw_token)
    if payload:
        user_id = payload.get("sub")
        if user_id and user_id == event.owner_id:
            return photo
            
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Unauthorized media access for this event",
    )
