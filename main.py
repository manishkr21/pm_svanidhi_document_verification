"""
Main entry point for fake document detection pipeline
"""

import logging
import sys

from fake_doc_detector.config import get_config
from fake_doc_detector.core import DetectionPipeline
from fake_doc_detector.core.document_types import DocumentType
from fake_doc_detector.loaders import LocalDocumentLoader


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging for the application"""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def print_usage():
    """Print usage instructions"""
    print("\nUsage: python main.py [document_type]")
    print("\nAvailable document types:")
    for doc_type in DocumentType:
        print(f"  - {doc_type.value}")
    print("\nExamples:")
    print("  python main.py                  # Process all document types")
    print("  python main.py aadhar           # Process only Aadhar documents")
    print("  python main.py pan              # Process only PAN documents")
    print("  python main.py ration_card      # Process only Ration Card documents")
    print("  python main.py voter_id         # Process only Voter ID documents")
    print()


def main():
    """Main execution function"""
    
    # Setup
    config = get_config()
    setup_logging(config.LOG_LEVEL)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("Fake Document Detection Pipeline - Starting")
    logger.info("=" * 60)
    
    try:
        # Create documents directory if it doesn't exist
        config.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for each document type
        for doc_type in DocumentType:
            type_dir = config.DOCUMENTS_DIR / doc_type.value
            type_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Ensured directory exists: {type_dir}")
        
        # Initialize document loader
        logger.info(f"Initializing document loader from: {config.DOCUMENTS_DIR}")
        loader = LocalDocumentLoader(str(config.DOCUMENTS_DIR))
        
        # Determine which document type(s) to process
        if len(sys.argv) > 1:
            doc_type_arg = sys.argv[1]
            if doc_type_arg.lower() == "voter_id":
                logger.info("Redirecting to automated Voter ID Excel verification script...")
                from fake_doc_detector.voter_id import verify_voter_id
                return verify_voter_id.main()
            elif doc_type_arg.lower() in [dt.value for dt in DocumentType]:
                # Process specific document type
                doc_type = DocumentType(doc_type_arg.lower())
                logger.info(f"Processing document type: {doc_type.value}")
                documents = loader.load_documents(doc_type)
            else:
                logger.error(f"Invalid document type: {doc_type_arg}")
                print_usage()
                return 1
        else:
            # Load all documents if no argument provided
            logger.info("Processing all document types")
            documents = loader.load_all_documents()
        
        if not documents:
            logger.warning("No documents found in the configured directories")
            logger.info("Please add document files to the following folders:")
            if len(sys.argv) > 1:
                doc_type = DocumentType(sys.argv[1].lower())
                type_dir = config.DOCUMENTS_DIR / doc_type.value
                logger.info(f"  - {type_dir}")
            else:
                for doc_type in DocumentType:
                    type_dir = config.DOCUMENTS_DIR / doc_type.value
                    logger.info(f"  - {type_dir}")
        
        # Initialize pipeline
        logger.info("Initializing detection pipeline")
        pipeline = DetectionPipeline(config=config.to_dict())
        
        # Load documents into pipeline
        if documents:
            pipeline.load_documents(documents)
        
        # Run detection
        results = pipeline.detect()
        
        logger.info("Detection pipeline execution completed")
        logger.info(f"Status: {results.get('status', 'unknown')}")
        summary = results.get("aadhar_summary")
        if summary:
            logger.info(
                "Aadhar summary | processed=%s ocr_success=%s numbers_found=%s valid=%s invalid=%s",
                summary.get("processed", 0),
                summary.get("ocr_success", 0),
                summary.get("numbers_found", 0),
                summary.get("valid_numbers", 0),
                summary.get("invalid_numbers", 0),
            )
        
        # Generate report
        report = pipeline.report()
        logger.info(f"\n{report}")
        
        logger.info("=" * 60)
        logger.info("Fake Document Detection Pipeline - Completed Successfully")
        logger.info("=" * 60)
        
        return 0
    
    except Exception as e:
        logger.error(f"Error during pipeline execution: {e}", exc_info=True)
        logger.error("=" * 60)
        logger.error("Fake Document Detection Pipeline - Failed")
        logger.error("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
