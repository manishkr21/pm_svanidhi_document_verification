"""Verhoeff checksum algorithm implementation for Aadhar number validation"""

import logging
from stdnum import verhoeff as stdnum_verhoeff

logger = logging.getLogger(__name__)


class VerhoeffValidator:
    """
    Verhoeff checksum algorithm for validating Aadhar numbers.
    
    The Verhoeff algorithm is a checksum algorithm that can detect
    most common transcription errors in numeric strings.
    
    This implementation uses the `stdnum` library's Verhoeff module
    which provides a proven, standard implementation.
    """
    
    @staticmethod
    def compute_checksum(digits: str) -> int:
        """
        Compute Verhoeff checksum for first 11 digits.
        
        Args:
            digits: First 11 digits of Aadhar number as string
        
        Returns:
            Checksum digit (0-9)
        """
        if len(digits) != 11:
            raise ValueError("Input must contain exactly 11 digits")
        
        if not digits.isdigit():
            raise ValueError("Input must contain only digits")
        
        try:
            # Compute the check digit using stdnum's verhoeff module
            check_digit = stdnum_verhoeff.calc_check_digit(digits)
            return int(check_digit)
        except Exception as e:
            logger.error(f"Error computing Verhoeff checksum: {e}")
            raise
    
    @staticmethod
    def validate(aadhar_number: str) -> bool:
        """
        Validate Aadhar number using Verhoeff algorithm.
        
        Args:
            aadhar_number: Full 12-digit Aadhar number as string
        
        Returns:
            True if valid, False otherwise
        """
        if len(aadhar_number) != 12:
            return False
        
        if not aadhar_number.isdigit():
            return False
        
        try:
            # Use stdnum's verhoeff validation
            return stdnum_verhoeff.is_valid(aadhar_number)
        except Exception as e:
            logger.error(f"Error validating Verhoeff checksum: {e}")
            return False
