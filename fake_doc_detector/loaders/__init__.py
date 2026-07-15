"""Document loaders for fetching documents from various sources"""

import logging
import os
from pathlib import Path
from typing import List, Optional

from fake_doc_detector.core.document_types import Document, DocumentType


logger = logging.getLogger(__name__)


class LocalDocumentLoader:
    """Loader for fetching documents from local file system"""
    
    SUPPORTED_FORMATS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}
    
    def __init__(self, base_path: str):
        """
        Initialize local document loader.
        
        Args:
            base_path: Root directory path for documents
        """
        self.base_path = Path(base_path)
        if not self.base_path.exists():
            raise FileNotFoundError(f"Base path does not exist: {base_path}")
        logger.info(f"LocalDocumentLoader initialized with path: {base_path}")
    
    def load_documents(
        self, 
        doc_type: DocumentType,
        subfolder: Optional[str] = None
    ) -> List[Document]:
        """
        Load documents of a specific type from local folder.
        
        Args:
            doc_type: Type of document to load
            subfolder: Optional subfolder within base_path
        
        Returns:
            List of Document objects
        """
        if subfolder:
            search_path = self.base_path / subfolder
        else:
            search_path = self.base_path / doc_type.value
        
        if not search_path.exists():
            logger.warning(f"Search path does not exist: {search_path}")
            return []
        
        documents = []
        
        for file_path in search_path.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in self.SUPPORTED_FORMATS:
                try:
                    doc = Document(
                        file_path=str(file_path),
                        doc_type=doc_type,
                        file_name=file_path.name
                    )
                    documents.append(doc)
                    logger.debug(f"Loaded document: {file_path.name}")
                except Exception as e:
                    logger.error(f"Error loading document {file_path}: {e}")
        
        logger.info(f"Loaded {len(documents)} {doc_type.value} documents")
        return documents
    
    def load_all_documents(self, subfolder: Optional[str] = None) -> List[Document]:
        """
        Load all documents from all document type folders.
        
        Args:
            subfolder: Optional subfolder within base_path
        
        Returns:
            List of all Document objects
        """
        all_documents = []
        
        for doc_type in DocumentType:
            documents = self.load_documents(doc_type, subfolder)
            all_documents.extend(documents)
        
        logger.info(f"Loaded total of {len(all_documents)} documents")
        return all_documents
