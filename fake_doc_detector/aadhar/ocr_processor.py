"""Aadhar specific OCR processor extending generic OCRExtractor"""

import logging
import re
from typing import Dict, List

from fake_doc_detector.utils.ocr_processor import OCRExtractor

logger = logging.getLogger(__name__)


class AadharOCRExtractor(OCRExtractor):
    """
    Extracts Aadhar numbers from document images using OCR.
    """
    
    # Regex pattern for Aadhar number: 12 digits starting with 2-9
    AADHAR_PATTERN = re.compile(r'\b[2-9]\d{11}\b')
    
    # Alternative patterns (with spaces or hyphens)
    AADHAR_PATTERN_FORMATTED = re.compile(r'\b(?<!\d[\s\-])[2-9]\d{3}[\s-]\d{4}[\s-]\d{4}\b(?![\s-]\d)')

    def __init__(self):
        super().__init__()
        logger.debug("AadharOCRExtractor initialized")

    def find_aadhar_numbers(self, text: str) -> List[Dict]:
        """
        Find Aadhar numbers in extracted text.
        """
        found_numbers = []
        
        if not text:
            return found_numbers
        
        # Search for standard format (12 consecutive digits)
        matches = self.AADHAR_PATTERN.finditer(text)
        for match in matches:
            number = match.group()
            found_numbers.append({
                "number": number,
                "position": match.start(),
                "format": "standard",
                "confidence": 0.95
            })
        
        # Search for formatted numbers (with spaces/hyphens)
        formatted_matches = self.AADHAR_PATTERN_FORMATTED.finditer(text)
        for match in formatted_matches:
            raw = match.group()
            # Clean the number
            cleaned = raw.replace(" ", "").replace("-", "")
            if len(cleaned) == 12 and cleaned[0] in "23456789":
                found_numbers.append({
                    "number": cleaned,
                    "position": match.start(),
                    "raw": raw,
                    "format": "formatted",
                    "confidence": 0.90
                })
        
        # Remove duplicates
        seen = set()
        unique_numbers = []
        for num_dict in found_numbers:
            if num_dict["number"] not in seen:
                seen.add(num_dict["number"])
                unique_numbers.append(num_dict)
        
        logger.info(f"Found {len(unique_numbers)} Aadhar numbers in text")
        return unique_numbers
    
    def extract_aadhar_from_image(self, image_path: str) -> Dict:
        """
        Complete pipeline: Extract text and find Aadhar numbers.
        """
        result = {
            "image_path": image_path,
            "success": False,
            "aadhar_numbers": [],
            "extracted_text": "",
            "errors": []
        }
        
        # Step 1: Extract text using OCR
        ocr_result = self.extract_text_from_image(image_path)
        result["extracted_text"] = ocr_result["extracted_text"]
        result["errors"].extend(ocr_result["errors"])
        
        # Step 2: Find Aadhar numbers in extracted text
        aadhar_numbers = []
        if ocr_result["success"]:
            aadhar_numbers = self.find_aadhar_numbers(ocr_result["extracted_text"])
            
        if aadhar_numbers:
            result["success"] = True
            result["aadhar_numbers"] = aadhar_numbers
            logger.info(f"Extracted {len(aadhar_numbers)} Aadhar numbers from image")
            # Clear initial errors if any (since we found numbers)
            result["errors"] = [err for err in result["errors"] if "No Aadhar numbers" not in err]
        else:
            # Fallback: Try adaptive thresholding if no numbers found in standard OCR
            logger.info(f"No Aadhar number found with standard OCR. Trying adaptive thresholding fallback for: {image_path}")
            try:
                import cv2
                from PIL import Image
                import pytesseract
                
                cv_img = cv2.imread(image_path)
                if cv_img is not None:
                    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
                    adaptive = cv2.adaptiveThreshold(
                        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
                    )
                    # Convert to PIL Image for pytesseract
                    pil_adaptive = Image.fromarray(adaptive)
                    adaptive_text = pytesseract.image_to_string(pil_adaptive)
                    
                    fallback_numbers = self.find_aadhar_numbers(adaptive_text)
                    if fallback_numbers:
                        result["success"] = True
                        result["aadhar_numbers"] = fallback_numbers
                        result["extracted_text"] = (result["extracted_text"] + "\n" + adaptive_text).strip()
                        logger.info(f"Successfully extracted {len(fallback_numbers)} Aadhar numbers using adaptive thresholding fallback")
                        return result
            except Exception as e:
                logger.error(f"Error during adaptive thresholding fallback for {image_path}: {e}")
            
            result["errors"].append("No Aadhar numbers found in extracted text")
        
        return result
