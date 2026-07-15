"""Generic QR Code scanner utility using OpenCV and zxing-cpp"""

import logging
from pathlib import Path
from typing import Optional

try:
    import cv2
    import zxingcpp
    import numpy as np
    HAS_QR_READER = True
except ImportError:
    HAS_QR_READER = False

logger = logging.getLogger(__name__)


class QRScanner:
    """
    Generic utility class for scanning QR codes from images or PDFs.
    """

    def __init__(self):
        self._scan_cache = {}
        logger.debug(f"QRScanner initialized (HAS_QR_READER: {HAS_QR_READER})")

    def scan_qr_code(self, image_path: str) -> Optional[str]:
        """
        Scan image and extract QR code payload. Caches results to avoid redundant scanning.

        Args:
            image_path: Path to document image file

        Returns:
            The raw text payload from the QR code, or None if not found
        """
        if not HAS_QR_READER:
            logger.warning("cv2 or zxing-cpp not installed. Cannot scan QR code.")
            return None

        try:
            abs_path = str(Path(image_path).resolve())
        except Exception:
            abs_path = image_path

        if abs_path in self._scan_cache:
            logger.debug(f"QR scan cache hit for: {abs_path}")
            return self._scan_cache[abs_path]

        result = self._scan_qr_code_impl(image_path)
        self._scan_cache[abs_path] = result
        return result

    def _scan_qr_code_impl(self, image_path: str) -> Optional[str]:
        """Scan image and extract QR code payload (implementation)."""
        try:
            path = Path(image_path)
            if not path.exists():
                logger.error(f"Image not found: {image_path}")
                return None

            # Check if file is a PDF
            if path.suffix.lower() == ".pdf":
                from fake_doc_detector.core.pdf_utils import extract_pdf_contents
                
                with extract_pdf_contents(image_path) as (_, image_paths):
                    for img_path in image_paths:
                        qr_text = self.scan_qr_code(str(img_path))
                        if qr_text:
                            return qr_text
                return None

            img = cv2.imread(image_path)
            if img is None:
                logger.error(f"Failed to read image using opencv: {image_path}")
                return None

            # Scan using zxing-cpp directly first
            results = zxingcpp.read_barcodes(img)
            if results:
                for result in results:
                    if "QR" in str(result.format):
                        logger.info(f"Successfully scanned QR code from {image_path}")
                        return result.text

            # Try robust preprocessing and scaling combination fallbacks
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            sharpen_kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])

            preprocessors = [
                ("grayscale", lambda g: g),
                ("CLAHE", lambda g: clahe.apply(g)),
                ("Otsu binarization", lambda g: cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
                ("Adaptive Thresholding", lambda g: cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)),
                ("Sharpening", lambda g: cv2.filter2D(g, -1, sharpen_kernel))
            ]

            for scale in [1.0, 2.0, 3.0]:
                try:
                    # Apply resizing once per scale level rather than inside the preprocessor loop
                    if scale != 1.0:
                        h, w = gray.shape[:2]
                        resized = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LANCZOS4)
                    else:
                        resized = gray
                except Exception:
                    continue

                for name, prep_func in preprocessors:
                    try:
                        # Apply preprocessor
                        processed = prep_func(resized)
                        
                        # Read barcodes
                        results = zxingcpp.read_barcodes(processed)
                        if results:
                            for result in results:
                                if "QR" in str(result.format):
                                    logger.info(f"Successfully scanned QR code using {name} preprocessing at {scale}x scale")
                                    return result.text
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"Error scanning QR code in {image_path}: {e}")

        return None
