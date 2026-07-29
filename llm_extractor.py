"""
llm_extractor.py

Anthropic Claude document extraction engine (defaulting to claude-fable-5).
Extracts structured JSON data directly from document files or OCR text using the Anthropic Messages API.
Supports printed text, handwritten text, Hindi (Devanagari), English, and multilingual documents.
Uses standard library urllib.request for zero-dependency HTTP REST API calls.
"""

import json
import re
import base64
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, Union

from config import logger, get_api_key, DEFAULT_MODEL, API_TIMEOUT
from prompts import DOCUMENT_EXTRACTION_PROMPT

RE_MARKDOWN_JSON = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

MIME_TYPE_MAP: Dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".webp": "image/webp"
}


class LLMExtractor:
    """Anthropic Claude LLM Extractor (claude-fable-5) with multilingual & handwriting support."""

    DEFAULT_MODEL = DEFAULT_MODEL
    ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or get_api_key()
        if not self.api_key:
            raise ValueError(
                "API_KEY environment variable is missing. "
                "Please set API_KEY in your .env file."
            )
        self.model = model or self.DEFAULT_MODEL

    def _clean_json_response(self, text: str) -> Dict[str, Any]:
        """Cleans and extracts JSON dictionary from LLM response text."""
        cleaned = text.strip()
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

    def _call_anthropic_api(
        self, 
        prompt: str, 
        image_base64: Optional[str] = None, 
        mime_type: Optional[str] = None, 
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Executes HTTP POST request to Anthropic Messages API."""
        target_model = model or self.model
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        if image_base64 and mime_type:
            block_type = "document" if mime_type == "application/pdf" else "image"
            user_content = [
                {
                    "type": block_type,
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": image_base64
                    }
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        else:
            user_content = prompt

        payload = {
            "model": target_model,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": user_content
                }
            ]
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.ANTHROPIC_URL, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                resp_bytes = resp.read()
                result_json = json.loads(resp_bytes.decode("utf-8"))
                
                content_blocks = result_json.get("content", [])
                text_response = ""
                for block in content_blocks:
                    if block.get("type") == "text":
                        text_response += block.get("text", "")
                
                usage = result_json.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                total_tokens = input_tokens + output_tokens
                logger.info("Anthropic API Token Usage - Input: %d, Output: %d, Total: %d", input_tokens, output_tokens, total_tokens)
                print(f"[LLM Token Usage] Input: {input_tokens} | Output: {output_tokens} | Total: {total_tokens}")

                if not text_response:
                    logger.warning("No text content returned from Anthropic API: %s", result_json)
                    return {"error": "No text content returned from Anthropic API", "details": result_json}
                
                return self._clean_json_response(text_response)

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            logger.error("Anthropic API HTTP Error %d %s: %s", e.code, e.reason, error_body)
            return {"error": f"Anthropic API HTTP Error {e.code}: {e.reason}", "details": error_body}
        except urllib.error.URLError as e:
            logger.error("Anthropic API URL Error: %s", e.reason)
            return {"error": f"Anthropic API URL Error: {str(e.reason)}"}
        except Exception as e:
            logger.error("Anthropic API Call Failed: %s", e)
            return {"error": f"Anthropic API Call Failed: {str(e)}"}

    def extract_from_text(self, text: str, model_override: Optional[str] = None) -> Dict[str, Any]:
        """
        Takes raw document OCR text (English, Hindi, or any language) and extracts structured JSON using Anthropic Claude.
        """
        if not text or not text.strip():
            return {"error": "No text provided for LLM extraction"}

        prompt = f"{DOCUMENT_EXTRACTION_PROMPT}\n\nDocument OCR Text:\n{text}"

        return self._call_anthropic_api(prompt=prompt, model=model_override)

    def extract_from_file(self, file_path: Union[str, Path], model_override: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts structured JSON directly from a document file (image or PDF).
        Supports printed text, handwritten text, Hindi (Devanagari), English, and any language natively.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error("File not found: %s", path)
            return {"error": f"File not found: {path}"}

        prompt = DOCUMENT_EXTRACTION_PROMPT

        suffix = path.suffix.lower()
        mime_type = MIME_TYPE_MAP.get(suffix, "image/jpeg")

        try:
            with open(path, "rb") as f:
                file_bytes = f.read()

            base64_data = base64.b64encode(file_bytes).decode("utf-8")

            return self._call_anthropic_api(
                prompt=prompt,
                image_base64=base64_data,
                mime_type=mime_type,
                model=model_override
            )
        except Exception as e:
            logger.error("Failed to read or encode file '%s': %s", path, e)
            return {"error": f"Failed to read file: {str(e)}"}
