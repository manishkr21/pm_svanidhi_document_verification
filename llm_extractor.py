"""
llm_extractor.py

Qwen/Qwen3-32B document extraction engine (vLLM OpenAI-compatible API).
Extracts structured JSON data directly from document OCR text using the vLLM API at http://172.31.102.10:8092/vllm_api/v1/chat/completions.
Supports printed text, handwritten text, Hindi (Devanagari), English, and multilingual documents.
Uses standard library urllib.request for zero-dependency HTTP REST API calls.
"""

import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, Union

from config import logger, get_api_key, DEFAULT_MODEL, QWEN_API_URL, API_TIMEOUT
from prompts import DOCUMENT_EXTRACTION_PROMPT
from document_processor import DocumentProcessor

RE_MARKDOWN_JSON = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
RE_THINK_BLOCK = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)


class LLMExtractor:
    """Qwen/Qwen3-32B LLM Extractor with multilingual & OCR document extraction support."""

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
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes HTTP POST request to Qwen vLLM OpenAI-compatible Chat Completions API."""
        target_model = model or self.model
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": target_model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
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
        Takes raw document OCR text (English, Hindi, or any language) and extracts structured JSON using Qwen/Qwen3-32B.
        """
        if not text or not text.strip():
            return {"error": "No text provided for LLM extraction"}

        prompt = f"{DOCUMENT_EXTRACTION_PROMPT}\n\nDocument OCR Text:\n{text}"

        return self._call_qwen_api(prompt=prompt, model=model_override)

    def extract_from_file(self, file_path: Union[str, Path], model_override: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts structured JSON directly from a document file by running OCR extraction and passing extracted text to Qwen/Qwen3-32B.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error("File not found: %s", path)
            return {"error": f"File not found: {path}"}

        try:
            ocr_result = self.processor.process(path)
            full_text = ocr_result.get("full_text", "")
            if not full_text:
                return {"error": f"No OCR text could be extracted from file '{path.name}'"}

            return self.extract_from_text(text=full_text, model_override=model_override)
        except Exception as e:
            logger.error("Failed to process file '%s': %s", path, e)
            return {"error": f"Failed to process file: {str(e)}"}
