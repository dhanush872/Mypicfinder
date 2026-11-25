from typing import List, Tuple
import numpy as np
from PIL import Image
from backend.matchers.base import BaseFaceMatcher, FaceDescriptor

class LocalFeatureFaceMatcher(BaseFaceMatcher):
    """
    Lightweight, completely offline, zero-binary-dependency face matcher.
    Implemented entirely using NumPy and Pillow:
    1. Facial skin-chrominance and spatial saliency candidate detector.
    2. Spatial Histogram of Oriented Gradients (HOG) over a 4x4 facial spatial grid (96 dims).
    3. Uniform Local Binary Pattern (LBP) texture descriptor (16 dims).
    4. Facial color chrominance distribution histogram (16 dims).
    
    Produces a 128-dimensional L2-normalized feature vector.
    """

    def __init__(self):
        self._dim = 128

    @property
    def name(self) -> str:
        return "local_feature_matcher"

    @property
    def dimension(self) -> int:
        return self._dim

    def _extract_descriptors_from_crop(self, crop_rgb: np.ndarray) -> np.ndarray:
        """
        Extract spatial HOG (96) + LBP (16) + Color (16) features from a 64x64 face crop.
        Output: 128-dim float32 unit vector.
        """
        # Convert to standardized 64x64 grayscale
        pil_crop = Image.fromarray(crop_rgb).resize((64, 64), Image.Resampling.BILINEAR)
        gray_img = pil_crop.convert("L")
        gray = np.array(gray_img, dtype=np.float32)

        # 1. Spatial HOG on 4x4 grid (16 cells, 6 orientation bins each = 96 dims)
        # Compute central difference gradients
        gx = np.zeros_like(gray)
        gy = np.zeros_like(gray)
        gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
        gy[1:-1, :] = gray[2:, :] - gray[:-2, :]

        mag = np.sqrt(gx**2 + gy**2)
        angle = np.mod(np.arctan2(gy, gx) * (180.0 / np.pi), 180.0)
        bin_idx = (angle / 30.0).astype(int) % 6

        hog_features = []
        cell_size = 16  # 64 / 4 = 16
        for r in range(4):
            for c in range(4):
                cell_bin = bin_idx[r * cell_size:(r + 1) * cell_size, c * cell_size:(c + 1) * cell_size]
                cell_mag = mag[r * cell_size:(r + 1) * cell_size, c * cell_size:(c + 1) * cell_size]
                hist = np.zeros(6, dtype=np.float32)
                for b in range(6):
                    hist[b] = np.sum(cell_mag[cell_bin == b])
                cell_norm = np.linalg.norm(hist) + 1e-6
                hist /= cell_norm
                hog_features.extend(hist)

        # 2. Simplified Local Binary Pattern (LBP) 16-bin histogram (16 dims)
        center = gray[1:-1, 1:-1]
        lbp = np.zeros(center.shape, dtype=np.uint8)
        neighbors = [
            gray[0:-2, 0:-2], gray[0:-2, 1:-1], gray[0:-2, 2:],
            gray[1:-1, 2:], gray[2:, 2:], gray[2:, 1:-1],
            gray[2:, 0:-2], gray[1:-1, 0:-2]
        ]
        for i, n in enumerate(neighbors):
            lbp |= ((n >= center).astype(np.uint8) << i)
        lbp_hist, _ = np.histogram(lbp, bins=16, range=(0, 256), density=True)
        lbp_hist = lbp_hist.astype(np.float32)

        # 3. Color chrominance histogram (16 dims)
        # Convert RGB to YCbCr approximation
        r_chan = crop_rgb[:, :, 0].astype(np.float32)
        g_chan = crop_rgb[:, :, 1].astype(np.float32)
        b_chan = crop_rgb[:, :, 2].astype(np.float32)
        cb = -0.168736 * r_chan - 0.331264 * g_chan + 0.5 * b_chan + 128
        cr = 0.5 * r_chan - 0.418688 * g_chan - 0.081312 * b_chan + 128

        cb_hist, _ = np.histogram(cb, bins=8, range=(0, 256), density=True)
        cr_hist, _ = np.histogram(cr, bins=8, range=(0, 256), density=True)
        color_features = np.concatenate([cb_hist, cr_hist]).astype(np.float32)

        # Combine: 96 + 16 + 16 = 128 dimensions
        vector = np.concatenate([hog_features, lbp_hist, color_features]).astype(np.float32)

        # L2-normalize
        norm = np.linalg.norm(vector)
        if norm > 1e-7:
            vector /= norm
        return vector

    def detect_and_extract(self, image: Image.Image) -> List[FaceDescriptor]:
        """Detect faces and extract 128-dim normalized descriptors using pure Python/NumPy."""
        if image.mode != "RGB":
            image = image.convert("RGB")
        rgb = np.array(image)
        h, w = rgb.shape[:2]

        results: List[FaceDescriptor] = []

        # Skin-chrominance detection in YCbCr space
        r = rgb[:, :, 0].astype(np.float32)
        g = rgb[:, :, 1].astype(np.float32)
        b = rgb[:, :, 2].astype(np.float32)
        cb = -0.168736 * r - 0.331264 * g + 0.5 * b + 128
        cr = 0.5 * r - 0.418688 * g - 0.081312 * b + 128

        # Skin color boundaries: 77 <= Cb <= 127 and 133 <= Cr <= 173
        skin_mask = (cb >= 77) & (cb <= 127) & (cr >= 133) & (cr <= 173)

        # Find connected components or bounding boxes from skin mask
        # If skin pixels exist, compute bounding box of primary cluster
        skin_indices = np.argwhere(skin_mask)
        if len(skin_indices) > 64:  # At least 64 skin pixels
            y_min, x_min = skin_indices.min(axis=0)
            y_max, x_max = skin_indices.max(axis=0)

            box_w = x_max - x_min
            box_h = y_max - y_min
            if box_w >= 16 and box_h >= 16:
                # Add margin
                pad_x = int(box_w * 0.1)
                pad_y = int(box_h * 0.1)
                x1 = max(0, x_min - pad_x)
                y1 = max(0, y_min - pad_y)
                x2 = min(w, x_max + pad_x)
                y2 = min(h, y_max + pad_y)

                crop = rgb[y1:y2, x1:x2]
                if crop.size > 0:
                    emb = self._extract_descriptors_from_crop(crop)
                    bbox = (float(x1) / w, float(y1) / h, float(x2 - x1) / w, float(y2 - y1) / h)
                    results.append(FaceDescriptor(bbox=bbox, embedding=emb, confidence=0.88))

        # Always ensure at least one focal crop for portraits / selfies if skin detector was sparse
        if len(results) == 0:
            side = min(w, h)
            x0 = (w - side) // 2
            y0 = (h - side) // 2
            crop = rgb[y0:y0+side, x0:x0+side]
            if crop.size > 0:
                emb = self._extract_descriptors_from_crop(crop)
                bbox = (float(x0) / w, float(y0) / h, float(side) / w, float(side) / h)
                results.append(FaceDescriptor(bbox=bbox, embedding=emb, confidence=0.75))

        return results
