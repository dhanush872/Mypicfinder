from typing import Optional
from backend.config import settings
from backend.matchers.base import BaseFaceMatcher, FaceDescriptor
from backend.matchers.deep_matcher import DeepFaceMatcher
from backend.matchers.local_matcher import LocalFeatureFaceMatcher

_cached_matcher: Optional[BaseFaceMatcher] = None

def get_face_matcher(backend: Optional[str] = None) -> BaseFaceMatcher:
    """
    Factory function returning the configured Face Matcher singleton.
    Options: 'local', 'deep', or 'auto'.
    """
    global _cached_matcher
    selected_backend = (backend or settings.FACE_MATCHER_BACKEND).lower()
    
    if _cached_matcher is not None and (_cached_matcher.name.startswith(selected_backend) or selected_backend == "auto"):
        return _cached_matcher
        
    if selected_backend == "local":
        _cached_matcher = LocalFeatureFaceMatcher()
    elif selected_backend == "deep":
        _cached_matcher = DeepFaceMatcher()
    else:  # auto
        # If ONNX model files exist in models/, prefer DeepFaceMatcher; else LocalFeatureFaceMatcher
        if (settings.MODELS_DIR / "arcface.onnx").exists():
            _cached_matcher = DeepFaceMatcher()
        else:
            _cached_matcher = LocalFeatureFaceMatcher()
            
    return _cached_matcher

__all__ = ["BaseFaceMatcher", "FaceDescriptor", "LocalFeatureFaceMatcher", "DeepFaceMatcher", "get_face_matcher"]
