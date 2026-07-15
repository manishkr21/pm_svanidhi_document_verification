"""Metadata and software detection analyzer for document files"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import PyPDF2
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


logger = logging.getLogger(__name__)


class MetadataAnalyzer:
    """
    Analyzes metadata and software detection in document images and PDFs.
    
    Detects:
    - Image EXIF metadata
    - PDF creation and modification software
    - Editing software traces (Photoshop, GIMP, etc.)
    - Compression artifacts
    - Modification timestamps
    """
    
    # Known editing software signatures
    EDITING_SOFTWARE = {
        "photoshop": ["Adobe Photoshop", "Photoshop", "PSVersion"],
        "gimp": ["GIMP", "GNU Image"],
        "paint": ["Paint", "MS Paint"],
        "paint.net": ["Paint.NET"],
        "imagemagick": ["ImageMagick"],
    }
    
    # Suspicious software indicators
    SUSPICIOUS_INDICATORS = [
        "photoshop",
        "gimp",
        "paint",
        "edit",
        "modified",
        "batch",
    ]
    
    @staticmethod
    def analyze_image(file_path: str) -> Dict:
        """
        Analyze metadata in image file.
        
        Args:
            file_path: Path to image file
        
        Returns:
            Dictionary with metadata information
        """
        result = {
            "file_path": file_path,
            "file_type": "image",
            "has_exif": False,
            "exif_data": {},
            "suspicious_software": [],
            "warnings": [],
            "is_potentially_fake": False,
            "risk_score": 0.0
        }
        
        if not HAS_PIL:
            logger.warning("PIL not installed. Image metadata analysis skipped.")
            result["warnings"].append("PIL library not available for full analysis")
            return result
        
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                result["warnings"].append(f"File not found: {file_path}")
                return result
            
            with Image.open(file_path) as img:
                # Check for EXIF data
                exif_data = img.getexif()
                
                if exif_data:
                    result["has_exif"] = True
                    
                    # Extract readable EXIF tags
                    for tag_id, value in exif_data.items():
                        tag_name = TAGS.get(tag_id, tag_id)
                        result["exif_data"][tag_name] = str(value)[:100]  # Truncate long values
                else:
                    result["warnings"].append("No EXIF data found - image may be stripped")
                    result["risk_score"] += 0.1
                
                # Check for suspicious EXIF values
                for key, value in result["exif_data"].items():
                    value_lower = str(value).lower()
                    
                    for software, keywords in MetadataAnalyzer.EDITING_SOFTWARE.items():
                        if any(kw.lower() in value_lower for kw in keywords):
                            result["suspicious_software"].append(software)
                            result["risk_score"] += 0.2
                            result["warnings"].append(f"Editing software detected: {software}")
                
                # Check image format and properties
                if img.format:
                    result["format"] = img.format
                    result["size"] = img.size
                
                # Detect re-saved images (common in forgery)
                if not exif_data and img.format == "JPEG":
                    result["warnings"].append("JPEG without EXIF - may be re-saved/edited")
                    result["risk_score"] += 0.15
        
        except Exception as e:
            logger.error(f"Error analyzing image {file_path}: {e}")
            result["warnings"].append(f"Error during analysis: {str(e)}")
            result["risk_score"] += 0.1
        
        # Determine if potentially fake
        if result["suspicious_software"] or result["risk_score"] > 0.3:
            result["is_potentially_fake"] = True
        
        return result
    
    @staticmethod
    def analyze_pdf(file_path: str) -> Dict:
        """
        Analyze metadata in PDF file.
        
        Args:
            file_path: Path to PDF file
        
        Returns:
            Dictionary with metadata information
        """
        result = {
            "file_path": file_path,
            "file_type": "pdf",
            "has_metadata": False,
            "metadata": {},
            "suspicious_software": [],
            "warnings": [],
            "is_potentially_fake": False,
            "risk_score": 0.0
        }
        
        if not HAS_PYPDF:
            logger.warning("PyPDF2 not installed. PDF metadata analysis skipped.")
            result["warnings"].append("PyPDF2 library not available for full analysis")
            return result
        
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                result["warnings"].append(f"File not found: {file_path}")
                return result
            
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                metadata = pdf_reader.metadata
                
                if metadata:
                    result["has_metadata"] = True
                    
                    for key, value in metadata.items():
                        result["metadata"][key] = str(value)
                else:
                    result["warnings"].append("No metadata found in PDF")
                    result["risk_score"] += 0.1
                
                # Check for suspicious creator software
                creator = result["metadata"].get("/Creator", "").lower()
                producer = result["metadata"].get("/Producer", "").lower()
                
                for software, keywords in MetadataAnalyzer.EDITING_SOFTWARE.items():
                    if any(kw.lower() in creator for kw in keywords) or \
                       any(kw.lower() in producer for kw in keywords):
                        result["suspicious_software"].append(software)
                        result["risk_score"] += 0.2
                        result["warnings"].append(f"Suspicious software detected: {software}")
                
                # Check for modification indicators
                creation_date = result["metadata"].get("/CreationDate")
                modification_date = result["metadata"].get("/ModDate")
                
                if creation_date and modification_date:
                    if creation_date != modification_date:
                        result["warnings"].append("PDF was modified after creation")
                        result["risk_score"] += 0.15
        
        except Exception as e:
            logger.error(f"Error analyzing PDF {file_path}: {e}")
            result["warnings"].append(f"Error during analysis: {str(e)}")
            result["risk_score"] += 0.1
        
        # Determine if potentially fake
        if result["suspicious_software"] or result["risk_score"] > 0.3:
            result["is_potentially_fake"] = True
        
        return result
    
    @staticmethod
    def analyze_file(file_path: str) -> Dict:
        """
        Analyze metadata in any supported file format.
        
        Args:
            file_path: Path to file
        
        Returns:
            Dictionary with metadata information
        """
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
            return MetadataAnalyzer.analyze_image(file_path)
        elif file_ext == '.pdf':
            return MetadataAnalyzer.analyze_pdf(file_path)
        else:
            return {
                "file_path": file_path,
                "file_type": "unsupported",
                "warnings": [f"Unsupported file format: {file_ext}"],
                "is_potentially_fake": False,
                "risk_score": 0.0
            }
