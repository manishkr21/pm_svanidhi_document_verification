"""OCR text extraction wrapper using pytesseract"""

import logging
from pathlib import Path
from typing import Dict

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

logger = logging.getLogger(__name__)


class OCRExtractor:
    """
    Extracts text from images or PDF documents using OCR (pytesseract).
    """

    def __init__(self):
        if not HAS_OCR:
            logger.warning("pytesseract or PIL not available. OCR extraction will not work.")
        logger.debug("OCRExtractor initialized")

    def extract_text_from_image(self, image_path: str) -> Dict:
        """
        Extract text from image using OCR.

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with extracted text and metadata
        """
        result = {
            "image_path": image_path,
            "success": False,
            "extracted_text": "",
            "confidence": 0.0,
            "errors": []
        }

        if not HAS_OCR:
            result["errors"].append("OCR libraries not installed (pytesseract, PIL)")
            return result

        try:
            image_path_obj = Path(image_path)
            if not image_path_obj.exists():
                result["errors"].append(f"File not found: {image_path}")
                return result

            # Check if file is a PDF
            if image_path_obj.suffix.lower() == ".pdf":
                from fake_doc_detector.core.pdf_utils import extract_pdf_contents
                
                pdf_text_parts = []
                with extract_pdf_contents(image_path) as (selectable_text, image_paths):
                    if selectable_text.strip():
                        pdf_text_parts.append(selectable_text)
                    
                    # Run OCR on all extracted/rendered images
                    for img_path in image_paths:
                        ocr_res = self.extract_text_from_image(str(img_path))
                        if ocr_res["success"] and ocr_res["extracted_text"].strip():
                            pdf_text_parts.append(ocr_res["extracted_text"])
                
                combined_text = "\n".join(pdf_text_parts)
                if combined_text.strip():
                    result["success"] = True
                    result["extracted_text"] = combined_text
                    result["confidence"] = 0.90
                    logger.debug(f"Successfully extracted text from PDF {image_path}")
                else:
                    result["errors"].append("No text extracted from PDF pages or images")
                return result

            # Open image
            img = Image.open(image_path)
            
            # Perform OCR
            extracted_text = pytesseract.image_to_string(img)
            
            if extracted_text.strip():
                result["success"] = True
                result["extracted_text"] = extracted_text
                result["confidence"] = 0.8  # Default confidence for OCR extraction
                logger.debug(f"Successfully extracted text from {image_path}")
            else:
                result["errors"].append("No text extracted from image")

        except Exception as e:
            logger.error(f"Error extracting text from {image_path}: {e}")
            result["errors"].append(f"OCR Error: {str(e)}")

        return result
