"""Core pipeline for Aadhar OCR and validation."""

from pathlib import Path
import textwrap
from typing import Dict, List
import logging

import re
from .document_types import Document
from .document_types import DocumentType
from fake_doc_detector.aadhar import AadharDetector, AadharOCRExtractor
from fake_doc_detector.pan import PANDetector



logger = logging.getLogger(__name__)


class DetectionPipeline:
    """Orchestrates OCR extraction and Aadhar verification."""
    
    def __init__(self, config: dict = None):
        """
        Initialize the detection pipeline.
        
        Args:
            config: Configuration dictionary for pipeline parameters
        """
        self.config = config or {}
        self.documents: List[Document] = []
        self.last_results: Dict = {}
        public_key_path = self.config.get("uidai_public_key_path")
        self.aadhar_detector = AadharDetector(public_key_path=public_key_path)
        self.pan_detector = PANDetector()
        self.ocr_extractor = AadharOCRExtractor()
        logger.info("DetectionPipeline initialized")
    
    def load_documents(self, documents: List[Document]) -> None:
        """
        Load documents into the pipeline.
        
        Args:
            documents: List of Document objects to process
        """
        self.documents = documents
        logger.info(f"Loaded {len(documents)} documents")
    
    def _process_aadhar_document(self, document: Document) -> Dict:
        """
        Run OCR and Aadhar validation for a single Aadhar document.

        Args:
            document: Document object for Aadhar type

        Returns:
            Dictionary containing per-document processing results
        """
        file_path = document.file_path
        file_suffix = Path(file_path).suffix.lower()
        image_formats = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".pdf"}

        result: Dict = {
            "file_name": document.file_name,
            "file_path": file_path,
            "ocr_success": False,
            "detected_numbers": [],
            "valid_numbers": [],
            "invalid_numbers": [],
            "errors": [],
        }

        if file_suffix not in image_formats:
            result["errors"].append(
                f"Unsupported OCR format for Aadhar flow: {file_suffix}. "
                "Supported formats are .png, .jpg, .jpeg, .tiff, .bmp, .pdf"
            )
            return result

        ocr_result = self.ocr_extractor.extract_aadhar_from_image(file_path)
        result["ocr_success"] = ocr_result.get("success", False)
        result["errors"].extend(ocr_result.get("errors", []))

        found_numbers = ocr_result.get("aadhar_numbers", [])
        result["detected_numbers"] = [num_info["number"] for num_info in found_numbers]

        for num_info in found_numbers:
            aadhar_number = num_info["number"]
            raw_match = num_info.get("raw") or num_info["number"]
            validation_result = self.aadhar_detector.detect(aadhar_number, file_path=file_path)
            number_result = {
                "aadhar_number": aadhar_number,
                "raw_match": f"Aadhar: {raw_match}",
                "status": validation_result.get("overall_status", "UNKNOWN"),
                "confidence": validation_result.get("confidence", 0.0),
                "is_fake": validation_result.get("is_fake", True),
                "messages": validation_result.get("messages", []),
            }

            if validation_result.get("overall_status") == "VALID":
                result["valid_numbers"].append(number_result)
            else:
                result["invalid_numbers"].append(number_result)

        if not found_numbers and not result["errors"]:
            result["errors"].append("No Aadhar numbers found in extracted text")

        return result

    def _process_pan_document(self, document: Document) -> Dict:
        """
        Run OCR and PAN validation for a single PAN document.

        Args:
            document: Document object for PAN type

        Returns:
            Dictionary containing per-document processing results
        """
        file_path = document.file_path
        file_suffix = Path(file_path).suffix.lower()
        image_formats = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".pdf"}

        result: Dict = {
            "file_name": document.file_name,
            "file_path": file_path,
            "ocr_success": False,
            "detected_numbers": [],
            "valid_numbers": [],
            "invalid_numbers": [],
            "errors": [],
        }

        if file_suffix not in image_formats:
            result["errors"].append(
                f"Unsupported OCR format for PAN flow: {file_suffix}. "
                "Supported formats are .png, .jpg, .jpeg, .tiff, .bmp, .pdf"
            )
            return result

        ocr_result = self.ocr_extractor.extract_text_from_image(file_path)
        result["ocr_success"] = ocr_result.get("success", False)
        result["errors"].extend(ocr_result.get("errors", []))

        extracted_text = ocr_result.get("extracted_text", "")
        
        # Find PAN numbers using robust finding with OCR error corrections
        from fake_doc_detector.pan import find_pan_numbers_in_text_with_raw, extract_demographics_from_text
        found_pans_info = find_pan_numbers_in_text_with_raw(extracted_text)
        found_pans = [item["corrected"] for item in found_pans_info]
        result["detected_numbers"] = found_pans
        
        # Create a mapping from corrected PAN to raw match
        pan_raw_map = {item["corrected"]: item["raw"] for item in found_pans_info}

        # Extract demographic details for verification logic
        visual_ocr_text = extract_demographics_from_text(extracted_text)

        # Fallback to "Unknown" if OCR could not find the PAN number
        pans_to_validate = found_pans if found_pans else ["Unknown"]

        number_results = []
        for pan_number in pans_to_validate:
            validation_result = self.pan_detector.detect(
                pan_number=pan_number, 
                file_path=file_path, 
                visual_ocr_text=visual_ocr_text
            )
            actual_pan = validation_result.get("pan_number", pan_number)
            raw_match = pan_raw_map.get(actual_pan, pan_raw_map.get(pan_number, "-"))
            if raw_match == "-" and actual_pan != "Unknown" and actual_pan != pan_number:
                raw_match = "(QR code only)"
            
            dob_val = visual_ocr_text.get("dob", "Unknown")
            name_val = visual_ocr_text.get("name", "Unknown")
            raw_details = f"PAN: {raw_match} | DOB: {dob_val} | Name: {name_val}"
            
            number_result = {
                "pan_number": actual_pan,
                "raw_match": raw_details,
                "status": validation_result.get("overall_status", "UNKNOWN"),
                "confidence": validation_result.get("confidence", 0.0),
                "is_fake": validation_result.get("is_fake", True),
                "messages": validation_result.get("messages", []),
            }
            number_results.append(number_result)

        # Select the single best validation result to report for the document
        if number_results:
            status_priority = {"VALID": 0, "POTENTIALLY_FAKE": 1, "REJECTED_FRAUD": 2, "INVALID": 3}
            # Sort by status (VALID first), then highest confidence, then fewest warning messages
            sorted_results = sorted(
                number_results,
                key=lambda x: (
                    status_priority.get(x["status"], 99),
                    -x["confidence"],
                    len([m for m in x["messages"] if "does not match" in m or "mismatch" in m])
                )
            )
            best_result = sorted_results[0]
            
            # Update detected numbers to contain only the resolved best PAN
            result["detected_numbers"] = [best_result["pan_number"]] if best_result["pan_number"] != "Unknown" else []
            
            # Clean up error messages if we successfully matched a number
            if best_result["pan_number"] != "Unknown":
                result["errors"] = [err for err in result["errors"] if "No PAN numbers" not in err]

            if best_result["status"] == "VALID":
                result["valid_numbers"].append(best_result)
            else:
                result["invalid_numbers"].append(best_result)

        if not result["detected_numbers"] and not result["errors"]:
            result["errors"].append("No PAN numbers found in extracted text or secure QR code")

        return result

    def detect(self) -> dict:
        """
        Run the detection pipeline.
        
        Returns:
            Dictionary with detection results (to be implemented)
        """
        logger.info("Starting detection pipeline...")
        
        if not self.documents:
            logger.warning("No documents loaded for detection")
            self.last_results = {}
            return self.last_results
        
        results = {
            "documents_processed": len(self.documents),
            "status": "completed",
            "message": "Detection completed",
            "aadhar_summary": {
                "processed": 0,
                "ocr_success": 0,
                "numbers_found": 0,
                "valid_numbers": 0,
                "invalid_numbers": 0,
            },
            "pan_summary": {
                "processed": 0,
                "ocr_success": 0,
                "numbers_found": 0,
                "valid_numbers": 0,
                "invalid_numbers": 0,
            },
            "document_results": [],
        }

        for document in self.documents:
            if document.doc_type == DocumentType.AADHAR:
                doc_result = self._process_aadhar_document(document)
                results["document_results"].append(doc_result)

                results["aadhar_summary"]["processed"] += 1
                if doc_result["ocr_success"]:
                    results["aadhar_summary"]["ocr_success"] += 1

                detected_count = len(doc_result["detected_numbers"])
                results["aadhar_summary"]["numbers_found"] += detected_count
                results["aadhar_summary"]["valid_numbers"] += len(doc_result["valid_numbers"])
                results["aadhar_summary"]["invalid_numbers"] += len(doc_result["invalid_numbers"])
            elif document.doc_type == DocumentType.PAN:
                doc_result = self._process_pan_document(document)
                results["document_results"].append(doc_result)

                results["pan_summary"]["processed"] += 1
                if doc_result["ocr_success"]:
                    results["pan_summary"]["ocr_success"] += 1

                detected_count = len(doc_result["detected_numbers"])
                results["pan_summary"]["numbers_found"] += detected_count
                results["pan_summary"]["valid_numbers"] += len(doc_result["valid_numbers"])
                results["pan_summary"]["invalid_numbers"] += len(doc_result["invalid_numbers"])
            else:
                logger.info(f"Skipping non-supported document in current flow: {document.file_name}")
                continue

        if results["aadhar_summary"]["processed"] == 0 and results["pan_summary"]["processed"] == 0:
            results["status"] = "no_supported_documents"
            results["message"] = "No Aadhar or PAN documents found in loaded document set"

        self.last_results = results
        return self.last_results
    
    def _format_table(self, headers: List[str], rows: List[List[str]], col_widths: List[int]) -> str:
        """
        Format headers and rows into a clean, text-based table with cell wrapping.
        """
        border = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
        header_border = "+" + "+".join("=" * (w + 2) for w in col_widths) + "+"
        
        table_lines = []
        table_lines.append(border)
        
        def format_row(cells: List[str]) -> List[str]:
            wrapped_cells = []
            max_lines = 1
            for cell_text, width in zip(cells, col_widths):
                if not cell_text:
                    wrapped = [""]
                else:
                    clean_text = " ".join(str(cell_text).split())
                    wrapped = textwrap.wrap(clean_text, width=width)
                    if not wrapped:
                        wrapped = [""]
                wrapped_cells.append(wrapped)
                max_lines = max(max_lines, len(wrapped))
            
            row_lines = []
            for line_idx in range(max_lines):
                line_parts = []
                for col_idx, width in enumerate(col_widths):
                    cell_lines = wrapped_cells[col_idx]
                    cell_line = cell_lines[line_idx] if line_idx < len(cell_lines) else ""
                    line_parts.append(f" {cell_line:<{width}} ")
                row_lines.append("|" + "|".join(line_parts) + "|")
            return row_lines

        table_lines.extend(format_row(headers))
        table_lines.append(header_border)
        
        for row in rows:
            table_lines.extend(format_row(row))
            table_lines.append(border)
            
        return "\n".join(table_lines)

    def report(self) -> str:
        """
        Generate a report of detection results.
        
        Returns:
            Formatted report string
        """
        logger.info("Generating report...")
        if not self.documents:
            return "No documents loaded."

        if not self.last_results:
            return "No detection results available. Run detect() first."

        summary = self.last_results.get("aadhar_summary", {})
        pan_summary = self.last_results.get("pan_summary", {})
        
        report_lines = [
            "========================================================================",
            "DOCUMENT PROCESSING SUMMARY REPORT",
            "========================================================================",
            "Aadhar Summary:",
            f"- Processed files: {summary.get('processed', 0)}",
            f"- OCR success: {summary.get('ocr_success', 0)}",
            f"- Numbers found: {summary.get('numbers_found', 0)}",
            f"- Valid numbers: {summary.get('valid_numbers', 0)}",
            f"- Invalid/suspicious numbers: {summary.get('invalid_numbers', 0)}",
            "",
            "PAN Summary:",
            f"- Processed files: {pan_summary.get('processed', 0)}",
            f"- OCR success: {pan_summary.get('ocr_success', 0)}",
            f"- Numbers found: {pan_summary.get('numbers_found', 0)}",
            f"- Valid numbers: {pan_summary.get('valid_numbers', 0)}",
            f"- Invalid/suspicious numbers: {pan_summary.get('invalid_numbers', 0)}",
            "========================================================================",
            "",
            "Detailed Document Results:"
        ]
        
        headers = ["Document", "OCR", "Raw Regex Details", "Doc Number", "Status", "Conf.", "Details / Errors"]
        col_widths = [20, 5, 28, 12, 17, 6, 32]
        
        rows = []
        for doc_res in self.last_results.get("document_results", []):
            doc_printed = False
            checks = doc_res.get("valid_numbers", []) + doc_res.get("invalid_numbers", [])
            if not checks:
                rows.append([
                    doc_res['file_name'],
                    str(doc_res['ocr_success']),
                    "-",
                    "-",
                    "-",
                    "-",
                    ", ".join(doc_res['errors']) if doc_res['errors'] else "No numbers found"
                ])
            else:
                for check in checks:
                    doc_num = check.get('aadhar_number') or check.get('pan_number') or "-"
                    raw_ocr = check.get('raw_match') or "-"
                    rows.append([
                        "" if doc_printed else doc_res['file_name'],
                        "" if doc_printed else str(doc_res['ocr_success']),
                        raw_ocr,
                        doc_num,
                        check['status'],
                        f"{check['confidence']:.2f}",
                        ", ".join(check['messages']) if check['messages'] else "Passed validation"
                    ])
                    doc_printed = True
                    
        table_str = self._format_table(headers, rows, col_widths)
        report_lines.append(table_str)
        
        return "\n".join(report_lines)
