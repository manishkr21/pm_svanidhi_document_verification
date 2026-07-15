"""Aadhar secure QR code validation and cryptographic signature verification"""

import gzip
import logging
import zlib
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import (
        load_pem_public_key,
        load_der_public_key,
    )
    from cryptography.x509 import (
        load_der_x509_certificate,
        load_pem_x509_certificate,
    )
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

from fake_doc_detector.utils.qr_scanner import QRScanner

logger = logging.getLogger(__name__)


class AadharQRValidator:
    """
    Validates Aadhar secure QR code data structures and cryptographic signatures.
    """

    def __init__(self, public_key_path: Optional[str] = None):
        """
        Initialize the validator.

        Args:
            public_key_path: Optional path to UIDAI public key certificate (.pem or .cer),
                             can be a single file path, directory path, or comma-separated list of paths.
        """
        self.public_key_path = public_key_path
        self.public_keys = []
        self.public_key = None
        self.qr_scanner = QRScanner()
        if HAS_CRYPTO and public_key_path:
            self._load_public_keys(public_key_path)

    def _load_public_keys(self, path_str: str) -> None:
        """Load public keys from file, directory, or comma-separated string of paths"""
        try:
            parts = [p.strip() for p in path_str.split(",") if p.strip()]
            for part in parts:
                path = Path(part)
                if not path.exists():
                    logger.debug(f"Key/Certificate path not found: {part}")
                    continue
                
                if path.is_dir():
                    logger.debug(f"Scanning directory for certificates: {part}")
                    for entry in path.iterdir():
                        if entry.is_file() and entry.suffix.lower() in (".cer", ".pem", ".crt", ".der"):
                            self._load_key_file(entry)
                else:
                    self._load_key_file(path)
                    
            # Set self.public_key for backward compatibility
            self.public_key = self.public_keys[0] if self.public_keys else None
            
            if self.public_keys:
                logger.info(f"Loaded {len(self.public_keys)} UIDAI public key certificates for signature validation")
            else:
                logger.warning("No UIDAI public key certificates loaded. QR signature checks will be skipped.")
        except Exception as e:
            logger.error(f"Error loading public keys from {path_str}: {e}")

    def _load_key_file(self, path: Path) -> None:
        """Load a single public key or certificate file and append to self.public_keys"""
        try:
            key_bytes = path.read_bytes()
            loaded_key = None
            
            # 1. Try loading as X.509 certificate first (DER/PEM)
            if HAS_CRYPTO:
                try:
                    cert = load_der_x509_certificate(key_bytes)
                    loaded_key = cert.public_key()
                    logger.debug(f"Loaded public key from DER X.509 certificate {path}")
                except Exception:
                    pass
                    
                if not loaded_key:
                    try:
                        cert = load_pem_x509_certificate(key_bytes)
                        loaded_key = cert.public_key()
                        logger.debug(f"Loaded public key from PEM X.509 certificate {path}")
                    except Exception:
                        pass

                # 2. Fallback to direct raw public keys (PEM/DER)
                if not loaded_key:
                    try:
                        loaded_key = load_pem_public_key(key_bytes)
                        logger.debug(f"Loaded PEM public key from {path}")
                    except Exception:
                        pass

                if not loaded_key:
                    try:
                        loaded_key = load_der_public_key(key_bytes)
                        logger.debug(f"Loaded DER public key from {path}")
                    except Exception:
                        pass
            
            if loaded_key:
                # Avoid duplicates
                if loaded_key not in self.public_keys:
                    self.public_keys.append(loaded_key)
            else:
                logger.error(f"Failed to parse public key/certificate file {path} as X.509 cert or raw key.")
        except Exception as e:
            logger.error(f"Error loading public key from {path}: {e}")

    def scan_qr_code(self, image_path: str) -> Optional[str]:
        """Wrapper method for backward compatibility"""
        return self.qr_scanner.scan_qr_code(image_path)

    def decode_large_integer(self, qr_text: str) -> Optional[bytes]:
        """
        Decode base-10 large integer string from secure QR code back to raw bytes.
        """
        try:
            # Strip whitespace
            cleaned_text = qr_text.strip()
            if not cleaned_text.isdigit():
                return cleaned_text.encode('utf-8')

            val = int(cleaned_text)
            # Convert to big-endian byte array
            byte_length = (val.bit_length() + 7) // 8
            return val.to_bytes(byte_length, "big")
        except Exception as e:
            logger.error(f"Failed to decode large integer from QR: {e}")
            return None

    def decompress_payload(self, compressed_bytes: bytes) -> Optional[bytes]:
        """
        Decompress the raw bytes payload using zlib or gzip.
        """
        try:
            return zlib.decompress(compressed_bytes)
        except Exception:
            try:
                return gzip.decompress(compressed_bytes)
            except Exception as e:
                logger.error(f"Decompression of QR payload failed: {e}")
                return None

    def verify_signature(self, data_payload: bytes, signature: bytes) -> Tuple[bool, str]:
        """
        Verify the mathematical RSA signature block of the data payload.
        """
        if not HAS_CRYPTO:
            return False, "cryptography library not installed"

        if not self.public_keys:
            return False, "No public key certificates loaded/configured"

        errors = []
        for idx, key in enumerate(self.public_keys):
            try:
                key.verify(
                    signature,
                    data_payload,
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
                return True, f"Valid signature verified with key #{idx+1} (PKCS1v15)"
            except InvalidSignature:
                try:
                    key.verify(
                        signature,
                        data_payload,
                        padding.PSS(
                            mgf=padding.MGF1(hashes.SHA256()),
                            salt_length=padding.PSS.MAX_LENGTH,
                        ),
                        hashes.SHA256()
                    )
                    return True, f"Valid signature verified with key #{idx+1} (PSS)"
                except InvalidSignature:
                    errors.append(f"Key #{idx+1} invalid check block")
                except Exception as e:
                    errors.append(f"Key #{idx+1} error (PSS): {str(e)}")
            except Exception as e:
                errors.append(f"Key #{idx+1} error (PKCS1v15): {str(e)}")

        return False, f"Signature verification failed on all {len(self.public_keys)} loaded keys. Details: {'; '.join(errors)}"

    def validate(self, file_path: str) -> Dict:
        """
        Scan and perform full cryptographic verification on the document.
        """
        result = {
            "check_name": "Aadhar QR Code Cryptographic Verification",
            "passed": False,
            "errors": [],
            "warnings": [],
            "details": {
                "qr_detected": False,
                "decoded_successfully": False,
                "signature_verified": False,
            }
        }

        # 1. Scan the image for QR Code
        qr_text = self.qr_scanner.scan_qr_code(file_path)
        if not qr_text:
            result["warnings"].append("No QR code detected in document image")
            result["details"]["qr_detected"] = False
            return result

        result["details"]["qr_detected"] = True

        # Check for older XML formatted QR code
        if qr_text.strip().startswith("<?xml") or "<PrintLetterBarcodeData" in qr_text:
            import xml.etree.ElementTree as ET
            try:
                xml_content = qr_text.strip()
                root = ET.fromstring(xml_content)
                if root.tag == "PrintLetterBarcodeData":
                    attribs = root.attrib
                    result["passed"] = True
                    result["details"]["qr_type"] = "XML"
                    result["details"]["decoded_successfully"] = True
                    result["details"]["demographics"] = attribs
                    result["details"]["uid"] = attribs.get("uid")
                    result["details"]["name"] = attribs.get("name")
                    result["details"]["dob"] = attribs.get("dob")
                    result["details"]["gender"] = attribs.get("gender")
                    result["warnings"].append("Older unsigned XML QR code format (cryptographic verification skipped)")
                    logger.info("Aadhar QR Code successfully parsed as older XML format")
                    return result
            except Exception as e:
                result["errors"].append(f"Failed to parse old Aadhar XML QR code: {e}")
                return result

        # 2. Convert base-10 integer string to compressed bytes
        compressed_bytes = self.decode_large_integer(qr_text)
        if not compressed_bytes:
            result["errors"].append("Failed to decode QR code integer payload")
            return result

        # 3. Decompress the payload
        decompressed = self.decompress_payload(compressed_bytes)
        if not decompressed:
            decompressed = compressed_bytes

        result["details"]["decoded_successfully"] = True

        # 4. Split data payload from the 256-byte signature block
        if len(decompressed) < 256:
            result["errors"].append(
                f"Decompressed payload length ({len(decompressed)}) too short to contain a signature block"
            )
            return result

        data_payload = decompressed[:-256]
        signature = decompressed[-256:]

        result["details"]["payload_size_bytes"] = len(data_payload)
        result["details"]["signature_size_bytes"] = len(signature)

        # 5. Cryptographic signature check (using RSA Verification)
        if not HAS_CRYPTO:
            result["errors"].append("cryptography module not installed - verification skipped")
            return result

        if not self.public_keys:
            result["warnings"].append("UIDAI public key certificates not configured; signature verification skipped")
            result["passed"] = False
            return result

        verified, msg = self.verify_signature(data_payload, signature)
        result["details"]["signature_verified"] = verified
        result["details"]["message"] = msg

        if verified:
            result["passed"] = True
            logger.info(f"Aadhar QR Code signature verified successfully: {msg}")
        else:
            result["errors"].append(f"Cryptographic signature check failed: {msg}")

        return result
