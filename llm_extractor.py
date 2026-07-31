"""
llm_extractor.py

Qwen/Qwen2.5-VL-32B-Instruct document extraction engine (vLLM OpenAI-compatible API).
Extracts structured JSON data directly from document OCR text using the vLLM API at http://172.31.102.10:8092/vllm_api/v1/chat/completions.
Supports printed text, handwritten text, Hindi (Devanagari), English, and multilingual documents.
Uses standard library urllib.request for zero-dependency HTTP REST API calls.
"""

import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

from config import logger, get_api_key, DEFAULT_MODEL, QWEN_API_URL, API_TIMEOUT
from prompts import DOCUMENT_EXTRACTION_PROMPT
from document_processor import DocumentProcessor

RE_MARKDOWN_JSON = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
RE_THINK_BLOCK = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)


def parse_ocr_text_to_dict(text: str) -> Dict[str, Any]:
    """
    Fallback parser that extracts structured key-value pairs and standard document patterns
    directly from raw OCR text when LLM API is unavailable.
    """
    data: Dict[str, Any] = {}
    if not text:
        return data

    for line in text.splitlines():
        line = line.strip()
        if ":" in line:
            parts = line.split(":", 1)
            key = parts[0].strip()
            val = parts[1].strip()
            if key and val and len(key) < 50:
                data[key] = val

    if "PANNumber" not in data and "pan" not in [k.lower() for k in data]:
        pan_match = re.search(r'\b[A-Z]{5}\d{4}[A-Z]\b', text)
        if pan_match:
            data["PANNumber"] = pan_match.group(0)

    if "AadhaarToken" not in data and "aadhaar" not in [k.lower() for k in data]:
        aadhaar_match = re.search(r'\b\d{12,14}\b', text)
        if aadhaar_match:
            data["AadhaarToken"] = aadhaar_match.group(0)

    if "MobileNo" not in data and "mobile" not in [k.lower() for k in data]:
        mobile_match = re.search(r'\b[6-9]\d{9}\b', text)
        if mobile_match:
            data["MobileNo"] = mobile_match.group(0)

    if "ApplicationNo" not in data:
        app_match = re.search(r'(?:Application\s*(?:Reference)?\s*No|App\s*No)[^\w:]*([A-Z0-9\/]+)', text, re.IGNORECASE)
        if app_match:
            data["ApplicationNo"] = app_match.group(1)

    if "ApplicationDate" not in data:
        date_match = re.search(r'(?:Date\s*of\s*Sanction|Application\s*Date|Date)[^\w:]*(\d{2}[\/\-\.]\d{2}[\/\-\.]\d{4}|\d{2}\-[A-Za-z]{3}\-\d{4})', text, re.IGNORECASE)
        if date_match:
            data["ApplicationDate"] = date_match.group(1)

    if "ApplicantName" not in data:
        name_match = re.search(r'(?:Borrower\s*Name|Applicant\s*Name|Name)[^\w:]*([A-Za-z\s]{3,40})', text, re.IGNORECASE)
        if name_match:
            data["ApplicantName"] = name_match.group(1).strip()

    return data


class LLMExtractor:
    """Qwen/Qwen2.5-VL-32B-Instruct LLM Extractor with multilingual & OCR document extraction support."""

    DEFAULT_MODEL = DEFAULT_MODEL
    QWEN_URL = QWEN_API_URL

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or get_api_key()
        self.model = model or self.DEFAULT_MODEL
        self.processor = DocumentProcessor(lang="eng")

    def _clean_json_response(self, text: str) -> Dict[str, Any]:
        """Cleans and extracts JSON dictionary from LLM response text, stripping reasoning <think> blocks if present."""
        cleaned = text.strip()
        # Remove reasoning <think>...</think> blocks from Qwen3/reasoning outputs
        cleaned = RE_THINK_BLOCK.sub("", cleaned).strip()

        if "```" in cleaned:
            match = RE_MARKDOWN_JSON.search(cleaned)
            if match:
                cleaned = match.group(1).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM response into JSON: %s", e)
            return {
                "error": f"Failed to parse LLM response into JSON: {str(e)}",
                "raw_response": text
            }

    def _call_qwen_api(
        self,
        prompt: str,
        images_base64: Optional[List[str]] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes HTTP POST request to Qwen vLLM OpenAI-compatible Chat Completions API."""
        target_model = model or self.model
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if images_base64:
            content_items: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
            for b64 in images_base64:
                content_items.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"}
                })
            messages_payload = [{"role": "user", "content": content_items}]
        else:
            messages_payload = [{"role": "user", "content": prompt}]

        payload = {
            "model": target_model,
            "messages": messages_payload,
            "temperature": 0.7,
            "max_tokens": 4096
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.QWEN_URL, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                resp_bytes = resp.read()
                result_json = json.loads(resp_bytes.decode("utf-8"))

                choices = result_json.get("choices", [])
                if not choices:
                    logger.warning("No choices returned from Qwen API: %s", result_json)
                    return {"error": "No text content returned from Qwen API", "details": result_json}

                text_response = choices[0].get("message", {}).get("content", "")

                usage = result_json.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", input_tokens + output_tokens)
                logger.info("Qwen API Token Usage - Input: %d, Output: %d, Total: %d", input_tokens, output_tokens, total_tokens)
                print(f"[Qwen Token Usage] Input: {input_tokens} | Output: {output_tokens} | Total: {total_tokens}")
                logger.info("LLM Response Text:\n%s", text_response)
                print(f"[LLM Extracted Text]:\n{text_response}")

                if not text_response:
                    logger.warning("Empty content returned from Qwen API: %s", result_json)
                    return {"error": "Empty text content returned from Qwen API", "details": result_json}

                return self._clean_json_response(text_response)

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else str(e)
            logger.error("Qwen API HTTP Error %d %s: %s", e.code, e.reason, error_body)
            return {"error": f"Qwen API HTTP Error {e.code}: {e.reason}", "details": error_body}
        except urllib.error.URLError as e:
            logger.error("Qwen API URL Error: %s", e.reason)
            return {"error": f"Qwen API URL Error: {str(e.reason)}"}
        except Exception as e:
            logger.error("Qwen API Call Failed: %s", e)
            return {"error": f"Qwen API Call Failed: {str(e)}"}

    def extract_from_text(self, text: str, model_override: Optional[str] = None) -> Dict[str, Any]:
        """
        Takes raw document OCR text (English, Hindi, or any language) and extracts structured JSON using Qwen/Qwen2.5-VL-32B-Instruct.
        """
        if not text or not text.strip():
            return {"error": "No text provided for LLM extraction"}

        prompt = f"{DOCUMENT_EXTRACTION_PROMPT}\n\nDocument OCR Text:\n{text}"

        return self._call_qwen_api(prompt=prompt, model=model_override)

    def extract_from_file(self, file_path: Union[str, Path], model_override: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts structured JSON directly from a document file.
        Attempts direct digital PDF text stream extraction first.
        If image or scanned PDF, attempts vision multimodal payload, falling back to Tesseract OCR text extraction.
        If LLM API is unavailable, falls back to Tesseract OCR structured pattern parsing.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error("File not found: %s", path)
            return {"error": f"File not found: {path}"}

        target_model = model_override or self.model

        try:
            # 1. If digital PDF with embedded text stream, extract text directly without Tesseract OCR
            if self.processor.is_pdf(path):
                direct_pdf_pages = self.processor.extract_text_from_pdf_direct(path)
                if direct_pdf_pages:
                    full_text = "\n\n".join([p["text"] for p in direct_pdf_pages if p["text"]])
                    if full_text and len(full_text.strip()) > 30:
                        logger.info("Extracted text stream directly from digital PDF '%s'. Bypassing Tesseract OCR.", path.name)
                        res = self.extract_from_text(text=full_text, model_override=model_override)
                        if "error" not in res:
                            res["_extraction_method"] = "pdf_text_stream + llm"
                            return res

                        fallback = parse_ocr_text_to_dict(full_text)
                        fallback["_extraction_method"] = "pdf_text_stream (llm unavailable)"
                        fallback["_llm_error"] = res.get("error")
                        fallback["raw_text"] = full_text
                        return fallback

            # 2. Try sending images directly via Vision API payload
            images_b64 = self.processor.process_images_base64(path)
            if images_b64:
                prompt = f"{DOCUMENT_EXTRACTION_PROMPT}\n\nPlease analyze the provided document image(s) directly and extract all holder-related attributes in structured JSON."
                res = self._call_qwen_api(prompt=prompt, images_base64=images_b64, model=model_override)
                if "error" not in res:
                    res["_extraction_method"] = f"llm direct vision ({target_model})"
                    return res
                logger.info("Vision API payload notice (%s). Falling back to OCR text extraction...", res.get("details", res.get("error")))

            # 3. Fallback to OCR text extraction (Tesseract OCR)
            ocr_result = self.processor.process(path)
            full_text = ocr_result.get("full_text", "")
            if not full_text:
                return {"error": f"No text could be extracted from file '{path.name}'"}

            res = self.extract_from_text(text=full_text, model_override=model_override)
            if "error" not in res:
                res["_extraction_method"] = f"tesseract_ocr + llm ({target_model})"
                return res

            logger.warning("LLM API call failed (%s). Returning Tesseract OCR extracted data fallback.", res.get("error"))
            fallback = parse_ocr_text_to_dict(full_text)
            fallback["_extraction_method"] = "tesseract_ocr (llm unavailable)"
            fallback["_llm_error"] = res.get("error")
            fallback["raw_ocr_text"] = full_text
            return fallback

        except Exception as e:
            logger.error("Failed to process file '%s': %s", path, e)
            return {"error": f"Failed to process file: {str(e)}"}
