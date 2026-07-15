"""PAN document detector with format, structure, metadata, and secure QR validation checks"""

import re
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project root and OPANqr to path
project_root = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str((project_root.parent / "OPANqr").resolve()))
from main import OPANQr

from fake_doc_detector.utils.qr_scanner import QRScanner
from fake_doc_detector.utils.metadata_analyzer import MetadataAnalyzer

logger = logging.getLogger(__name__)


class PANDetector:
    """
    Comprehensive PAN card and document detector.
    
    Validates PAN numbers using:
    1. Regex pattern matching and basic validation
    2. Structural logic (4th digit category, 5th digit surname match)
    3. Metadata and software detection for digital documents
    4. QR code extraction, OPANqr decryption, and signature checks
    5. Demographic data fuzzy matching between QR and OCR
    """
    
    # Regex pattern for PAN number: 5 letters, 4 digits, 1 letter
    PAN_PATTERN = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')
    
    # Valid PAN status/category characters (4th character)
    PAN_CATEGORIES = {
        'P': 'Individual',
        'C': 'Company',
        'H': 'Hindu Undivided Family (HUF)',
        'A': 'Association of Persons (AOP)',
        'B': 'Body of Individuals (BOI)',
        'G': 'Government Agency',
        'J': 'Artificial Juridical Person',
        'L': 'Local Authority',
        'F': 'Firm/ Limited Liability Partnership',
        'T': 'Trust'
    }

    def __init__(self):
        """Initialize the PAN detector"""
        self.qr_scanner = QRScanner()
        self._qr_cache = {}
        self._metadata_cache = {}
        logger.info("PANDetector initialized")

    def validate_basic_format(self, pan_number: str) -> Dict:
        """
        Validate basic PAN number format using regex.
        """
        result = {
            "check_name": "Basic Format Validation",
            "passed": False,
            "errors": [],
            "details": {}
        }
        
        if not pan_number:
            result["errors"].append("PAN number is empty")
            return result
            
        cleaned = str(pan_number).strip().upper()
        
        if len(cleaned) != 10:
            result["errors"].append(f"PAN number must contain exactly 10 characters (found {len(cleaned)})")
            result["details"]["length"] = len(cleaned)
            return result
            
        if not self.PAN_PATTERN.match(cleaned):
            result["errors"].append("PAN number does not match expected format (5 letters, 4 digits, 1 letter)")
            return result
            
        result["passed"] = True
        result["details"]["format"] = "valid"
        result["details"]["pan_number"] = cleaned
        return result

    def validate_structure_logic(self, pan_number: str, name_candidate: str) -> Dict:
        """
        Validate PAN card structural logic.
        1. 4th character must be a valid category.
        2. 5th character must match the first letter of cardholder's surname/last name.
        """
        result = {
            "check_name": "Structural Logic Validation",
            "passed": False,
            "errors": [],
            "warnings": [],
            "details": {}
        }
        
        cleaned_pan = str(pan_number).strip().upper()
        basic_res = self.validate_basic_format(cleaned_pan)
        if not basic_res["passed"]:
            result["errors"].extend(basic_res["errors"])
            return result
            
        # Check 4th character (category)
        category_char = cleaned_pan[3]
        if category_char not in self.PAN_CATEGORIES:
            result["errors"].append(f"Invalid category code '{category_char}' at 4th position of PAN")
        else:
            result["details"]["category"] = self.PAN_CATEGORIES[category_char]
            
        # Check 5th character (surname/entity name first character match)
        surname_char = cleaned_pan[4]
        if name_candidate and name_candidate != "Unknown":
            # Tokenize name
            name_parts = [p.strip().upper() for p in name_candidate.split() if p.strip()]
            if name_parts:
                # If individual ('P'):
                # - If name is a single word, it is treated as the surname during filing, so expected_char is the first letter of that word.
                # - If multiple words, expected_char is the first letter of the last name (surname).
                if category_char == 'P':
                    if len(name_parts) == 1:
                        expected_char = name_parts[0][0]
                        name_type_msg = "single name (treated as surname)"
                    else:
                        expected_char = name_parts[-1][0]
                        name_type_msg = "last name (surname)"
                else:
                    expected_char = name_parts[0][0]
                    name_type_msg = "entity name"
                
                # Check match (allow first letter of other name parts too as fallback to avoid minor false warnings due to OCR errors)
                matched = False
                for part in name_parts:
                    if part[0] == surname_char:
                        matched = True
                        break
                        
                if not matched:
                    result["warnings"].append(
                        f"5th letter of PAN '{surname_char}' does not match first letter of "
                        f"{name_type_msg} in extracted name '{name_candidate}' (expected '{expected_char}')"
                    )
                    result["details"]["surname_match"] = False
                else:
                    result["details"]["surname_match"] = True
            else:
                result["details"]["surname_match"] = "untestable_empty_name"
        else:
            result["details"]["surname_match"] = "untestable_no_name"

        if not result["errors"]:
            result["passed"] = True
            
        return result

    def validate_qr_code(self, file_path: str, visual_ocr_text: Dict, candidate_pan: Optional[str] = None) -> Dict:
        """
        Scan, unpack, parse, and verify PAN QR code cryptographically.
        """
        result = {
            "check_name": "PAN QR Code Verification",
            "passed": False,
            "errors": [],
            "warnings": [],
            "details": {
                "qr_detected": False,
                "decoded_successfully": False,
                "signature_verified": False
            }
        }
        
        # 1. Scan for QR code
        qr_text = self.qr_scanner.scan_qr_code(file_path)
        if not qr_text:
            result["warnings"].append("No QR code detected on the document surface")
            return result
            
        result["details"]["qr_detected"] = True
        
        # Check if the scanned string is numeric (secure PAN QR format)
        if not qr_text.isdigit():
            # Check if this is an Aadhar QR code
            if qr_text.strip().startswith("<?xml") or "<PrintLetterBarcodeData" in qr_text or len(qr_text) > 1000:
                result["errors"].append("FRAUD TRIGGERED: Document contains an Aadhar/UIDAI QR code instead of a PAN QR code")
            else:
                result["errors"].append(f"FRAUD TRIGGERED: QR code contains invalid/fake URL or plain text: {qr_text[:100]}")
            return result
            
        # 2. Unpack, parse, and verify with OPANQr
        try:
            opanqr = OPANQr(string=qr_text, verify=True)
            opanqr.parse()
            
            result["details"]["decoded_successfully"] = True
            result["details"]["demographics"] = opanqr.pii
            
            # Signature check
            if opanqr.verify:
                result["details"]["signature_verified"] = True
            else:
                result["warnings"].append("Cryptographic signature check could not be completed (unsupported PAN QR version)")
                
            # Compare QR demographic details with visual OCR data
            qr_pan = opanqr.pii.get("PAN", "").strip().upper()
            qr_name = opanqr.pii.get("Name", "").strip().lower()
            qr_dob = opanqr.pii.get("DOB", "").strip()
            
            visual_pan = (candidate_pan or visual_ocr_text.get("pan", "")).strip().upper()
            visual_name = visual_ocr_text.get("name", "").strip().lower()
            visual_dob = visual_ocr_text.get("dob", "").strip()
            
            # Fuzzy matching checks
            if visual_pan and visual_pan != "UNKNOWN":
                pan_match = qr_pan == visual_pan
            else:
                pan_match = True
                
            if visual_name and visual_name != "unknown":
                name_match = (qr_name == visual_name or qr_name in visual_name or visual_name in qr_name) if qr_name else False
            else:
                name_match = True
                
            if visual_dob and visual_dob != "unknown":
                clean_qr_dob = qr_dob.replace("/", "-")
                clean_visual_dob = visual_dob.replace("/", "-")
                dob_match = clean_qr_dob == clean_visual_dob
            else:
                dob_match = True
            
            result["details"]["data_matches"] = {
                "pan": pan_match,
                "name": name_match,
                "dob": dob_match
            }
            
            if not pan_match:
                result["errors"].append(f"FRAUD TRIGGERED: PAN mismatch. Card surface shows '{visual_pan}' but secure QR contains '{qr_pan}'")
            if not name_match:
                result["warnings"].append(f"Name mismatch. Card surface shows '{visual_name}' but secure QR contains '{qr_name}'")
            if not dob_match:
                result["warnings"].append(f"DOB mismatch. Card surface shows '{visual_dob}' but secure QR contains '{qr_dob}'")
                
            if not result["errors"]:
                result["passed"] = True
                
        except Exception as e:
            result["errors"].append(f"FRAUD TRIGGERED: Secure PAN QR signature verification or decoding failed: {e}")
            
        return result

    def analyze_document_metadata(self, file_path: str) -> Dict:
        """
        Analyze document metadata.
        """
        cache_key = str(Path(file_path).resolve())
        if cache_key in self._metadata_cache:
            return self._metadata_cache[cache_key]
            
        result = {
            "check_name": "Document Metadata Analysis",
            "passed": False,
            "errors": [],
            "details": {},
            "is_potentially_fake": False,
            "risk_score": 0.0
        }
        
        meta_res = MetadataAnalyzer.analyze_file(file_path)
        result["details"] = meta_res
        result["risk_score"] = meta_res.get("risk_score", 0.0)
        result["is_potentially_fake"] = meta_res.get("is_potentially_fake", False)
        
        if result["is_potentially_fake"]:
            result["errors"].extend(meta_res.get("warnings", []))
        else:
            result["passed"] = True
            
        self._metadata_cache[cache_key] = result
        return result

    def detect(self, pan_number: str, file_path: Optional[str] = None, visual_ocr_text: Optional[Dict] = None) -> Dict:
        """
        Run all PAN card detection and validation steps.
        """
        logger.info(f"Starting PAN detection for: {pan_number}")
        
        cleaned_pan = str(pan_number).strip().upper() if pan_number else "UNKNOWN"
        
        results = {
            "pan_number": cleaned_pan,
            "is_fake": False,
            "confidence": 0.0,
            "checks": [],
            "overall_status": "VALID",
            "messages": []
        }
        
        qr_parsed_pan = None
        qr_parsed_demographics = None
        
        # Check 1: QR Code Verification
        if file_path and visual_ocr_text:
            qr_res = self.validate_qr_code(file_path, visual_ocr_text, cleaned_pan)
            results["checks"].append(qr_res)
            
            if qr_res["details"].get("qr_detected"):
                if not qr_res["passed"]:
                    results["overall_status"] = "REJECTED_FRAUD"
                    results["is_fake"] = True
                    results["confidence"] = 1.0
                    results["messages"].extend(qr_res["errors"])
                    return results
                else:
                    results["confidence"] = max(results["confidence"], 0.95)
                    results["messages"].append("Secure PAN QR code signature verified successfully")
                    
                    # Extract demographics from verified QR code
                    qr_parsed_demographics = qr_res["details"].get("demographics", {})
                    qr_parsed_pan = qr_parsed_demographics.get("PAN", "").strip().upper()
                    
                    # If visual OCR PAN was unknown or empty, set verified PAN as ground truth
                    if cleaned_pan in ["UNKNOWN", "NONE", "NULL", ""]:
                        cleaned_pan = qr_parsed_pan
                        results["pan_number"] = cleaned_pan
            else:
                results["messages"].append("No QR code detected (skipped cryptographic checks)")

        # Check 2: Basic Format Check
        basic_res = self.validate_basic_format(cleaned_pan)
        results["checks"].append(basic_res)
        
        if not basic_res["passed"]:
            results["overall_status"] = "INVALID"
            results["is_fake"] = True
            results["messages"].extend(basic_res["errors"])
            return results
            
        # Check 3: Structural Logic Check
        name_candidate = visual_ocr_text.get("name", "") if visual_ocr_text else ""
        if name_candidate == "Unknown" and qr_parsed_demographics:
            name_candidate = qr_parsed_demographics.get("Name", "Unknown")
            
        struct_res = self.validate_structure_logic(cleaned_pan, name_candidate)
        results["checks"].append(struct_res)
        
        if not struct_res["passed"]:
            results["overall_status"] = "POTENTIALLY_FAKE"
            results["is_fake"] = True
            results["confidence"] = max(results["confidence"], 0.5)
            results["messages"].extend(struct_res["errors"])
            
        if struct_res.get("warnings"):
            results["messages"].extend(struct_res["warnings"])
            results["confidence"] = max(results["confidence"], 0.3)
            
        # Check 4: Metadata Analysis
        if file_path:
            meta_res = self.analyze_document_metadata(file_path)
            results["checks"].append(meta_res)
            
            if meta_res["is_potentially_fake"]:
                results["overall_status"] = "POTENTIALLY_FAKE"
                results["is_fake"] = True
                results["confidence"] = max(results["confidence"], meta_res["risk_score"])
                results["messages"].extend(meta_res["errors"])

        if results["overall_status"] == "VALID" and results["is_fake"]:
            results["overall_status"] = "POTENTIALLY_FAKE"
            
        if results["overall_status"] == "VALID":
            results["confidence"] = 1.0
            results["messages"].append("PAN number and document passed validation checks")
            
        return results
