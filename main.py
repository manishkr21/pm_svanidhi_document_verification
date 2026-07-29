"""
main.py

FastAPI application for End-to-End Document OCR and Structured Data Extraction.
Uses Anthropic Claude LLM for dynamic JSON document extraction via file upload.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field

from config import logger, get_api_key, DEFAULT_MODEL, DEFAULT_PORT
from document_processor import DocumentProcessor
from llm_extractor import LLMExtractor

app = FastAPI(
    title="Document OCR & Extractor API",
    description="FastAPI service for document OCR and Anthropic Claude LLM structured data extraction via file upload.",
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
    for schema in openapi_schema.get("components", {}).get("schemas", {}).values():
        if isinstance(schema, dict) and "properties" in schema:
            for prop in schema["properties"].values():
                if prop.get("type") == "array" and "items" in prop:
                    prop["items"]["format"] = "binary"
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

processor = DocumentProcessor(lang="eng")

# Helper to lazily get LLMExtractor
_llm_extractor: Optional[LLMExtractor] = None


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


def get_llm_extractor(model: str = DEFAULT_MODEL) -> LLMExtractor:
    """Returns an instance of LLMExtractor."""
    global _llm_extractor
    api_key = get_api_key()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="API_KEY environment variable is missing in .env or environment."
        )
    try:
        return LLMExtractor(api_key=api_key, model=model)
    except Exception as e:
        logger.error("Failed to initialize LLMExtractor: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize LLMExtractor: {str(e)}"
        )


@app.get("/", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Health check endpoint."""
    has_llm_key = bool(get_api_key())
    return HealthResponse(
        status="ok",
        service="Document Extractor API",
        language="eng",
        llm_available=has_llm_key
    )


@app.post("/extract", response_model=List[ExtractResponse])
async def extract_document(
    files: List[UploadFile] = File(..., description="One or more document files (PDF or Images)"),
    model: str = Query(DEFAULT_MODEL, description=f"Anthropic Claude model (default: {DEFAULT_MODEL})")
) -> List[ExtractResponse]:
    """
    Accepts document file uploads (Images or PDFs), performs OCR, and extracts dynamic JSON data via Anthropic Claude LLM.
    Processes each document separately and sends individual LLM calls.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    results: List[ExtractResponse] = []
    allowed_exts = processor.SUPPORTED_IMAGE_EXTS.union({".pdf"})

    for file in files:
        if not file.filename:
            results.append(ExtractResponse(
                filename="unknown",
                total_pages=0,
                extraction_method="none",
                data={"error": "No filename provided"}
            ))
            continue

        suffix = Path(file.filename).suffix.lower()
        if suffix not in allowed_exts:
            results.append(ExtractResponse(
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

            ocr_result = processor.process(tmp_file_path)

            llm = get_llm_extractor(model=model)
            structured_data = llm.extract_from_file(tmp_file_path, model_override=model)
            if "error" in structured_data and ocr_result.get("full_text"):
                structured_data = llm.extract_from_text(ocr_result.get("full_text", ""), model_override=model)
            extraction_method = f"llm ({model})"

            results.append(ExtractResponse(
                filename=file.filename,
                total_pages=ocr_result.get("total_pages", 1),
                extraction_method=extraction_method,
                data=structured_data
            ))

        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to process document '%s': %s", file.filename, e, exc_info=True)
            results.append(ExtractResponse(
                filename=file.filename,
                total_pages=0,
                extraction_method="error",
                data={"error": f"Failed to process document: {str(e)}"}
            ))

        finally:
            if tmp_file_path and tmp_file_path.exists():
                tmp_file_path.unlink(missing_ok=True)

    return results


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
