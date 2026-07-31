"""
main.py

FastAPI application for End-to-End Document OCR and Structured Data Extraction.
Uses Qwen/Qwen3-32B LLM (vLLM) for dynamic JSON document extraction via file upload.
"""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Form
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field

from config import logger, get_api_key, DEFAULT_MODEL, DEFAULT_PORT
from document_processor import DocumentProcessor
from llm_extractor import LLMExtractor

app = FastAPI(
    title="Document OCR & Extractor API",
    description="FastAPI service for document OCR and Qwen/Qwen3-32B LLM structured data extraction via file upload.",
    version="2.1.0"
)


def custom_openapi() -> Dict[str, Any]:
    """Custom OpenAPI schema generator to ensure Swagger UI displays file upload pickers for file arrays."""
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    for schema_name, schema in openapi_schema.get("components", {}).get("schemas", {}).items():
        if isinstance(schema, dict) and "properties" in schema:
            if "files" in schema["properties"]:
                prop = schema["properties"]["files"]
                desc = prop.get("description", "One or more document files (PDF or Images)") if isinstance(prop, dict) else "One or more document files (PDF or Images)"
                schema["properties"]["files"] = {
                    "type": "array",
                    "items": {"type": "string", "format": "binary"},
                    "title": "Files",
                    "description": desc
                }
            for prop in schema["properties"].values():
                if isinstance(prop, dict):
                    if prop.get("type") == "array" and "items" in prop:
                        prop["items"]["format"] = "binary"
                    elif "anyOf" in prop:
                        for item in prop["anyOf"]:
                            if isinstance(item, dict) and item.get("type") == "array" and "items" in item:
                                item["items"]["format"] = "binary"
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

processor = DocumentProcessor(lang="eng")

# Helper to lazily get LLMExtractor
_llm_extractor: Optional[LLMExtractor] = None


from verifier import DocumentVerifier

verifier = DocumentVerifier()


class HealthResponse(BaseModel):
    status: str
    service: str
    language: str
    llm_available: bool


class ExtractResponse(BaseModel):
    filename: str
    total_pages: int
    extraction_method: str
    data: Dict[str, Any]


class VerificationResultResponse(BaseModel):
    person_id: Optional[str] = None
    confidence_score: float
    total_ground_truth_fields: int
    matched_count: int
    mismatch_count: int
    missing_count: int
    net_score: float
    matched_fields: List[Dict[str, Any]]
    mismatched_fields: List[Dict[str, Any]]
    missing_fields: List[Dict[str, Any]]
    summary: str


class ExtractionPipelineResponse(BaseModel):
    extractions: List[ExtractResponse]
    verification_report: Optional[VerificationResultResponse] = None


def get_llm_extractor(model: str = DEFAULT_MODEL) -> LLMExtractor:
    """Returns an instance of LLMExtractor for Qwen/Qwen3-32B."""
    try:
        return LLMExtractor(api_key=get_api_key(), model=model)
    except Exception as e:
        logger.error("Failed to initialize LLMExtractor: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize LLMExtractor: {str(e)}"
        )


@app.get("/", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        service="Document Extractor API (Qwen/Qwen3-32B)",
        language="eng",
        llm_available=True
    )


@app.post("/extract", response_model=ExtractionPipelineResponse)
async def extract_document(
    user_detail: str = Form(..., description="JSON string or dict containing person details (ground truth) for verification"),
    files: List[UploadFile] = File(..., description="One or more document files (PDF or Images)"),
    model: str = Query(DEFAULT_MODEL, description=f"LLM model (default: {DEFAULT_MODEL})")
) -> ExtractionPipelineResponse:
    """
    Accepts document file uploads (Images or PDFs) and user_detail ground truth JSON string/dict.
    Performs OCR and extracts dynamic JSON data via Qwen/Qwen3-32B LLM.
    Matches extracted details against user_detail, flagging mismatches and calculating a confidence score.
    """
    if not files:
        raise HTTPException(
            status_code=400,
            detail="No document files provided. Please upload document files."
        )

    user_detail_dict: Dict[str, Any] = {}
    if isinstance(user_detail, str):
        try:
            user_detail_dict = json.loads(user_detail)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON string format for 'user_detail': {str(e)}"
            )
    elif isinstance(user_detail, dict):
        user_detail_dict = user_detail
    else:
        raise HTTPException(
            status_code=400,
            detail="'user_detail' must be a valid JSON string or dictionary."
        )

    if not isinstance(user_detail_dict, dict):
        raise HTTPException(
            status_code=400,
            detail="'user_detail' JSON must represent a dictionary of key-value pairs."
        )

    extractions: List[ExtractResponse] = []
    allowed_exts = processor.SUPPORTED_IMAGE_EXTS.union({".pdf"})

    for file in files:
        if not file.filename:
            extractions.append(ExtractResponse(
                filename="unknown",
                total_pages=0,
                extraction_method="none",
                data={"error": "No filename provided"}
            ))
            continue

        suffix = Path(file.filename).suffix.lower()
        if suffix not in allowed_exts:
            extractions.append(ExtractResponse(
                filename=file.filename,
                total_pages=0,
                extraction_method="none",
                data={"error": f"Unsupported file format '{suffix}'. Allowed: PDF, {', '.join(sorted(processor.SUPPORTED_IMAGE_EXTS))}"}
            ))
            continue

        tmp_file_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(file.file, tmp)
                tmp_file_path = Path(tmp.name)

            llm = get_llm_extractor(model=model)
            structured_data = llm.extract_from_file(tmp_file_path, model_override=model)
            method = structured_data.pop("_extraction_method", f"llm ({model})")
            total_pages = len(processor.load_document(tmp_file_path))

            extractions.append(ExtractResponse(
                filename=file.filename,
                total_pages=total_pages,
                extraction_method=method,
                data=structured_data
            ))

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to process uploaded file '%s': %s", file.filename, e, exc_info=True)
            extractions.append(ExtractResponse(
                filename=file.filename,
                total_pages=0,
                extraction_method="error",
                data={"error": f"Failed to process document: {str(e)}"}
            ))
        finally:
            if tmp_file_path and tmp_file_path.exists():
                tmp_file_path.unlink(missing_ok=True)

    # Perform verification against user_detail
    verification_report: Optional[VerificationResultResponse] = None
    try:
        extraction_dicts = [e.dict() for e in extractions]
        v_report = verifier.verify_extractions(user_detail=user_detail_dict, document_extractions=extraction_dicts)
        verification_report = VerificationResultResponse(**v_report)
    except Exception as e:
        logger.error("Verification failed for user_detail: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Verification failed: {str(e)}")

    return ExtractionPipelineResponse(
        extractions=extractions,
        verification_report=verification_report
    )


def find_available_port(default_port: int = DEFAULT_PORT) -> int:
    import socket
    for p in range(default_port, default_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', p))
                return p
            except OSError:
                continue
    return default_port


if __name__ == "__main__":
    import uvicorn
    actual_port = find_available_port(DEFAULT_PORT)
    logger.info("Starting Document Extractor API on http://0.0.0.0:%d", actual_port)
    uvicorn.run("main:app", host="0.0.0.0", port=actual_port, reload=True)
