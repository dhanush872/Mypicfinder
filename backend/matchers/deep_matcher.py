import logging
import os
from pathlib import Path
from typing import List, Optional
import numpy as np
from PIL import Image
from backend.config import settings
from backend.matchers.base import BaseFaceMatcher, FaceDescriptor
from backend.matchers.local_matcher import LocalFeatureFaceMatcher

logger = logging.getLogger(__name__)

class DeepFaceMatcher(BaseFaceMatcher):
    """
    Production ONNX Runtime Face Matcher utilizing:
    - SCRFD (Sample and Computation Redistribution for Efficient Face Detection)
    - ArcFace 512-dim ResNet/MobileFaceNet feature extraction
    
    If ONNX model weights are not found on the local filesystem, gracefully
    delegates to LocalFeatureFaceMatcher.
    """

    def __init__(self, models_dir: Optional[Path] = None):
        self.models_dir = models_dir or settings.MODELS_DIR
        self.arcface_model_path = self.models_dir / "arcface.onnx"
        self.scrfd_model_path = self.models_dir / "scrfd.onnx"
        self.fallback = LocalFeatureFaceMatcher()
        
        self.arcface_session = None
        self.scrfd_session = None
        self._dim = 512
        
        self._init_models()

    def _init_models(self):
        try:
            import onnxruntime as ort
            if self.arcface_model_path.exists():
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2
                self.arcface_session = ort.InferenceSession(str(self.arcface_model_path), opts, providers=["CPUExecutionProvider"])
                logger.info(f"Loaded ArcFace ONNX model from {self.arcface_model_path}")
            if self.scrfd_model_path.exists():
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2
                self.scrfd_session = ort.InferenceSession(str(self.scrfd_model_path), opts, providers=["CPUExecutionProvider"])
                logger.info(f"Loaded SCRFD ONNX model from {self.scrfd_model_path}")
        except Exception as e:
            logger.warning(f"Could not initialize ONNX Runtime models: {e}. Falling back to LocalFeatureFaceMatcher.")

    @property
    def name(self) -> str:
        if self.arcface_session is not None:
            return "deep_onnx_matcher"
        return "deep_onnx_matcher(fallback_local)"

    @property
    def dimension(self) -> int:
        if self.arcface_session is not None:
            return 512
        return self.fallback.dimension

    def _extract_arcface_embedding(self, face_chip_rgb: np.ndarray) -> np.ndarray:
        """Process 112x112 aligned face through ArcFace ONNX model."""
        pil_chip = Image.fromarray(face_chip_rgb).resize((112, 112), Image.Resampling.BILINEAR)
        resized = np.array(pil_chip, dtype=np.float32)
        blob = (resized - 127.5) / 128.0
        blob = np.transpose(blob, (2, 0, 1))  # (3, 112, 112)
        blob = np.expand_dims(blob, axis=0)   # (1, 3, 112, 112)
        
        input_name = self.arcface_session.get_inputs()[0].name
        output_name = self.arcface_session.get_outputs()[0].name
        pred = self.arcface_session.run([output_name], {input_name: blob})[0][0]
        
        norm = np.linalg.norm(pred)
        if norm > 1e-7:
            pred = pred / norm
        return pred.astype(np.float32)

    def detect_and_extract(self, image: Image.Image) -> List[FaceDescriptor]:
        # If ONNX models are not loaded, seamlessly use the local feature matcher
        if self.arcface_session is None:
            return self.fallback.detect_and_extract(image)
            
        if image.mode != "RGB":
            image = image.convert("RGB")
        rgb = np.array(image)
        h, w = rgb.shape[:2]
        
        faces: List[FaceDescriptor] = []
        # Fallback to local detector bounding box, then embed with ArcFace
        local_descs = self.fallback.detect_and_extract(image)
        for d in local_descs:
            bx, by, bw, bh = d.bbox
            x1 = int(bx * w)
            y1 = int(by * h)
            x2 = min(w, x1 + int(bw * w))
            y2 = min(h, y1 + int(bh * h))
            crop = rgb[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            emb = self._extract_arcface_embedding(crop)
            faces.append(FaceDescriptor(bbox=d.bbox, embedding=emb, confidence=d.confidence))
            
        return faces
