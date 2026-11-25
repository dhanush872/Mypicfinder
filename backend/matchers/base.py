from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
from PIL import Image

@dataclass
class FaceDescriptor:
    """Represents a detected face with normalized bounding box, embedding, and confidence."""
    bbox: Tuple[float, float, float, float]  # (x, y, w, h) in normalized coordinates [0.0, 1.0]
    embedding: np.ndarray                    # 1D float32 normalized unit vector (L2 norm = 1.0)
    confidence: float                        # Detection confidence score [0.0, 1.0]

class BaseFaceMatcher(ABC):
    """Abstract interface for face detection and embedding extraction engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the face matcher engine."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the feature embedding vector."""
        pass

    @abstractmethod
    def detect_and_extract(self, image: Image.Image) -> List[FaceDescriptor]:
        """
        Detect faces in the given PIL image and return their feature descriptors.
        Must operate entirely in memory.
        """
        pass

    def compute_similarity(self, query_embedding: np.ndarray, candidate_embeddings: np.ndarray) -> np.ndarray:
        """
        Compute cosine similarity between a single query vector (1D) and an array of candidate vectors (2D).
        Because both query and candidates are L2-normalized unit vectors,
        cosine similarity reduces to the matrix-vector dot product: S = C . q
        Returns a 1D float32 array of similarity scores in [-1.0, 1.0].
        """
        if candidate_embeddings.ndim == 1:
            candidate_embeddings = candidate_embeddings.reshape(1, -1)
            
        # Fast vectorized matrix-vector multiplication
        q = query_embedding.astype(np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm > 1e-7:
            q = q / q_norm
            
        c = candidate_embeddings.astype(np.float32)
        c_norms = np.linalg.norm(c, axis=1, keepdims=True)
        c_norms[c_norms < 1e-7] = 1e-7
        c_normalized = c / c_norms
        
        sims = np.dot(c_normalized, q)
        return np.clip(sims, -1.0, 1.0)
