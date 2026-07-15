"""Document type definitions and enums"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class DocumentType(Enum):
    """Supported document types for detection"""
    
    AADHAR = "aadhar"
    PAN = "pan"
    RATION_CARD = "ration_card"
    VOTER_ID = "voter_id"


@dataclass
class Document:
    """Document object for processing"""
    
    file_path: str
    doc_type: DocumentType
    file_name: str
    content: Optional[bytes] = None
    
    def __post_init__(self):
        if not self.file_path:
            raise ValueError("file_path cannot be empty")
    
    def __repr__(self) -> str:
        return f"Document(type={self.doc_type.value}, file={self.file_name})"
