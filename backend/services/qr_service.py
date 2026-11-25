import io
import cv2
import numpy as np
from PIL import Image

class QRService:
    """
    Generates pixel-perfect PNG and SVG QR codes for guest event access.
    Completely offline, zero-dependency implementation utilizing opencv-python QRCodeEncoder.
    """

    @staticmethod
    def _get_qr_matrix(text: str) -> np.ndarray:
        """Encode text into a 2D binary numpy matrix of 0s and 1s."""
        encoder = cv2.QRCodeEncoder.create()
        # Returns a 2D numpy array where modules are either 0 or 255 (or 1)
        matrix = encoder.encode(text)
        if matrix is None:
            # Fallback for unexpected encoder behavior
            raise ValueError("Failed to encode text to QR code")
        # Normalize to 0 (white) and 1 (black)
        return (matrix > 0).astype(np.uint8)

    @classmethod
    def generate_png(cls, text: str, module_size: int = 12, border: int = 4) -> bytes:
        """
        Generate pixel-perfect high resolution PNG QR code.
        module_size: pixel width of each QR module
        border: quiet zone module count (standard is 4)
        """
        matrix = cls._get_qr_matrix(text)
        h, w = matrix.shape
        
        full_w = (w + 2 * border) * module_size
        full_h = (h + 2 * border) * module_size
        
        # Create RGB image with white background
        img = Image.new("RGB", (full_w, full_h), (255, 255, 255))
        pixels = img.load()
        
        for r in range(h):
            for c in range(w):
                if matrix[r, c] == 1:
                    # Draw black square
                    x_start = (c + border) * module_size
                    y_start = (r + border) * module_size
                    for py in range(y_start, y_start + module_size):
                        for px in range(x_start, x_start + module_size):
                            pixels[px, py] = (17, 24, 39)  # Deep sleek dark gray/black #111827
                            
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()

    @classmethod
    def generate_svg(cls, text: str, border: int = 4) -> str:
        """
        Generate resolution-independent, crisp vector SVG QR code string.
        """
        matrix = cls._get_qr_matrix(text)
        h, w = matrix.shape
        full_w = w + 2 * border
        full_h = h + 2 * border
        
        path_segments = []
        for r in range(h):
            for c in range(w):
                if matrix[r, c] == 1:
                    x = c + border
                    y = r + border
                    path_segments.append(f"M{x},{y}h1v1h-1z")
                    
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {full_w} {full_h}" '
            f'shape-rendering="crispEdges" width="100%" height="100%">'
            f'<rect width="{full_w}" height="{full_h}" fill="#ffffff"/>'
            f'<path d="{" ".join(path_segments)}" fill="#111827"/>'
            f'</svg>'
        )
        return svg
