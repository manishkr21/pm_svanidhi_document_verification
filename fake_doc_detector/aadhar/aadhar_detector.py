"""Aadhar document detector with multiple validation checks"""

import re
import logging
from typing import Dict, List, Optional
from pathlib import Path

from fake_doc_detector.aadhar.verhoeff import VerhoeffValidator
from fake_doc_detector.utils.metadata_analyzer import MetadataAnalyzer
from fake_doc_detector.aadhar.qr_validator import AadharQRValidator

logger = logging.getLogger(__name__)


class AadharDetector:
    """
    Comprehensive Aadhar number and document detector.
    
    Validates Aadhar numbers using:
    1. Regex pattern matching and basic validation
    2. Verhoeff checksum algorithm
    3. Metadata and software detection for digital documents
    4. QR code extraction and cryptographic RSA verification
    """
    
    # Regex pattern for Aadhar number: starts with 2-9, followed by 11 digits
    AADHAR_PATTERN = re.compile(r'^[2-9][0-9]{11}$')
    
    def __init__(self, public_key_path: Optional[str] = None):
        """Initialize the Aadhar detector"""
        self.qr_validator = AadharQRValidator(public_key_path=public_key_path)
        self._qr_cache = {}
        self._metadata_cache = {}
        logger.info("AadharDetector initialized")
    
    def validate_basic_format(self, aadhar_number: str) -> Dict:
        """
        Validate basic Aadhar number format using regex.
        """
        result = {
            "check_name": "Basic Format Validation",
            "passed": False,
            "errors": [],
            "details": {}
        }
        
        if not aadhar_number:
            result["errors"].append("Aadhar number is empty")
            return result
        
        # Remove spaces and hyphens if any
        cleaned = aadhar_number.replace(" ", "").replace("-", "")
        
        # Check if only digits
        if not cleaned.isdigit():
            result["errors"].append("Aadhar number contains non-numeric characters")
            result["details"]["input"] = aadhar_number
            return result
        
        # Check length
        if len(cleaned) != 12:
            result["errors"].append(f"Aadhar number must contain exactly 12 digits (found {len(cleaned)})")
            result["details"]["length"] = len(cleaned)
            return result
        
        # Check first digit
        first_digit = int(cleaned[0])
        if first_digit in [0, 1]:
            result["errors"].append(f"First digit cannot be 0 or 1 (found {first_digit})")
            result["details"]["first_digit"] = first_digit
            return result
        
        # Check regex pattern
        if not self.AADHAR_PATTERN.match(cleaned):
            result["errors"].append("Aadhar number does not match expected pattern")
            return result
        
        # All checks passed
        result["passed"] = True
        result["details"]["format"] = "valid"
        result["details"]["aadhar_number"] = cleaned
        
        logger.debug(f"Basic format validation passed for: {cleaned}")
        return result
    
    def validate_checksum(self, aadhar_number: str) -> Dict:
        """
        Validate Aadhar number using Verhoeff checksum algorithm.
        """
        result = {
            "check_name": "Verhoeff Checksum Validation",
            "passed": False,
            "errors": [],
            "details": {}
        }
        
        if not aadhar_number:
            result["errors"].append("Aadhar number is empty")
            return result
        
        # Clean the input
        cleaned = aadhar_number.replace(" ", "").replace("-", "")
        
        # First verify basic format
        basic_result = self.validate_basic_format(cleaned)
        if not basic_result["passed"]:
            result["errors"].extend(basic_result["errors"])
            return result
        
        try:
            # Verify using Verhoeff algorithm
            is_valid = VerhoeffValidator.validate(cleaned)
            
            if is_valid:
                result["passed"] = True
                result["details"]["algorithm"] = "Verhoeff"
                result["details"]["status"] = "Valid checksum"
                logger.debug(f"Checksum validation passed for: {cleaned}")
            else:
                result["errors"].append("Checksum validation failed - invalid check digit")
                result["details"]["algorithm"] = "Verhoeff"
                result["details"]["status"] = "Invalid checksum"
        
        except Exception as e:
            result["errors"].append(f"Error during checksum validation: {str(e)}")
            logger.error(f"Checksum validation error for {cleaned}: {e}")
        
        return result
    
    def analyze_document_metadata(self, file_path: str) -> Dict:
        """
        Analyze metadata and software detection in document image/PDF.
        """
        if not file_path:
            return {
                "check_name": "Document Metadata Analysis",
                "passed": False,
                "errors": ["File path is empty"],
                "details": {},
                "is_potentially_fake": False,
                "risk_score": 0.0
            }
            
        cache_key = str(Path(file_path).resolve())
        if cache_key in self._metadata_cache:
            logger.debug(f"Metadata analysis cache hit for: {file_path}")
            return self._metadata_cache[cache_key]

        result = {
            "check_name": "Document Metadata Analysis",
            "passed": False,
            "errors": [],
            "details": {},
            "is_potentially_fake": False,
            "risk_score": 0.0
        }
        
        # Check if file exists
        if not Path(file_path).exists():
            result["errors"].append(f"File not found: {file_path}")
            return result
        
        # Analyze metadata
        metadata_result = MetadataAnalyzer.analyze_file(file_path)
        
        result["details"] = metadata_result
        result["risk_score"] = metadata_result.get("risk_score", 0.0)
        result["is_potentially_fake"] = metadata_result.get("is_potentially_fake", False)
        
        # Determine pass/fail
        if not metadata_result.get("is_potentially_fake") and result["risk_score"] < 0.3:
            result["passed"] = True
        else:
            result["errors"].extend(metadata_result.get("warnings", []))
            
        self._metadata_cache[cache_key] = result
        return result
    
    def validate_qr_code(self, file_path: str) -> Dict:
        """
        Scan and cryptographically verify QR code in document.
        """
        if not file_path:
            return {
                "check_name": "Aadhar QR Code Cryptographic Verification",
                "passed": False,
                "errors": ["File path is empty"],
                "warnings": [],
                "details": {
                    "qr_detected": False,
                    "decoded_successfully": False,
                    "signature_verified": False,
                }
            }
            
        cache_key = str(Path(file_path).resolve())
        if cache_key in self._qr_cache:
            logger.debug(f"QR verification cache hit for: {file_path}")
            return self._qr_cache[cache_key]
            
        validation_result = self.qr_validator.validate(file_path)
        self._qr_cache[cache_key] = validation_result
        return validation_result
    
    def detect(self, aadhar_number: str, file_path: Optional[str] = None) -> Dict:
        """
        Perform complete Aadhar detection and validation.
        """
        logger.info(f"Starting Aadhar detection for: {aadhar_number}")
        
        results = {
            "aadhar_number": aadhar_number.replace(" ", "").replace("-", ""),
            "is_fake": False,
            "confidence": 0.0,
            "checks": [],
            "overall_status": "VALID",
            "messages": []
        }
        
        # Check 1: Basic Format Validation
        basic_result = self.validate_basic_format(aadhar_number)
        results["checks"].append(basic_result)
        
        if not basic_result["passed"]:
            results["overall_status"] = "INVALID"
            results["is_fake"] = True
            results["messages"].extend(basic_result["errors"])
            logger.info(f"Basic format validation failed: {basic_result['errors']}")
            return results
        
        # Check 2: Verhoeff Checksum Validation
        checksum_result = self.validate_checksum(aadhar_number)
        results["checks"].append(checksum_result)
        
        if not checksum_result["passed"]:
            results["overall_status"] = "POTENTIALLY_FAKE"
            results["is_fake"] = True
            results["confidence"] = 0.85
            results["messages"].extend(checksum_result["errors"])
            logger.info(f"Checksum validation failed: {checksum_result['errors']}")
            
            # Return early if checksum fails
            if not file_path:
                return results
        
        # Check 3: Metadata Analysis (if file provided)
        if file_path:
            metadata_result = self.analyze_document_metadata(file_path)
            results["checks"].append(metadata_result)
            
            if metadata_result["is_potentially_fake"]:
                results["overall_status"] = "POTENTIALLY_FAKE"
                results["is_fake"] = True
                results["confidence"] = max(results["confidence"], metadata_result["details"].get("risk_score", 0.0))
                results["messages"].extend(metadata_result["errors"])
                logger.info(f"Metadata analysis detected potential forgery: {metadata_result['errors']}")
        
        # Check 4: QR Code Cryptographic Verification (if file provided)
        if file_path:
            qr_result = self.validate_qr_code(file_path)
            results["checks"].append(qr_result)
            
            if qr_result["details"].get("qr_detected"):
                if not qr_result["passed"]:
                    results["overall_status"] = "POTENTIALLY_FAKE"
                    results["is_fake"] = True
                    results["confidence"] = max(results["confidence"], 0.95)
                    results["messages"].extend(qr_result["errors"])
                    logger.info(f"QR cryptographic signature validation failed: {qr_result['errors']}")
                else:
                    if qr_result["details"].get("qr_type") == "XML":
                        xml_uid = qr_result["details"].get("uid")
                        cleaned_xml_uid = xml_uid.replace(" ", "").replace("-", "") if xml_uid else ""
                        cleaned_input_number = aadhar_number.replace(" ", "").replace("-", "")
                        if cleaned_xml_uid != cleaned_input_number:
                            results["overall_status"] = "POTENTIALLY_FAKE"
                            results["is_fake"] = True
                            results["confidence"] = max(results["confidence"], 0.95)
                            results["messages"].append(f"Aadhar number mismatch: OCR shows {cleaned_input_number} but QR code XML shows {cleaned_xml_uid}")
                        else:
                            results["confidence"] = max(results["confidence"], 0.90)
                            results["messages"].append("Older unsigned Aadhar XML QR code verified against OCR details")
                    else:
                        results["confidence"] = max(results["confidence"], 1.0)
                        results["messages"].append("Aadhar secure QR code cryptographically verified")
            else:
                results["messages"].append("No QR code detected (skipped cryptographic verification)")
        
        # Final confidence score
        if results["overall_status"] == "VALID":
            if results["confidence"] == 0.0:
                results["confidence"] = 1.0
            results["messages"].append("Aadhar number passed all validation checks")
            logger.info(f"Aadhar validation successful: {results['aadhar_number']}")
        
        return results
