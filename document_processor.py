"""
document_processor.py

Handles document ingestion (Images and PDFs), PDF text stream extraction,
PDF-to-Image rendering fallback for scanned documents, image preprocessing,
automatic orientation detection (0°, 90°, 180°, 270°), and OCR execution.
"""

import io
import base64
import tempfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Union
from PIL import Image, ImageEnhance, ImageOps

from config import logger, TESSDATA_DIR, SUPPORTED_IMAGE_EXTS

try:
    import pypdfium2 as pdfium
    HAS_PYPDFIUM2 = True
except ImportError:
    HAS_PYPDFIUM2 = False

try:
    from pdf2image import convert_from_path
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

try:
    import pytesseract
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False


class DocumentProcessor:
    """Processes document files (Images and PDFs) and performs OCR/text extraction."""

    SUPPORTED_IMAGE_EXTS = SUPPORTED_IMAGE_EXTS

    def __init__(self, tesseract_cmd: str = None, lang: str = "eng+hin"):
        if tesseract_cmd and HAS_PYTESSERACT:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            self.tesseract_bin = tesseract_cmd
        else:
            self.tesseract_bin = "tesseract"

        self.tessdata_dir = str(TESSDATA_DIR) if TESSDATA_DIR else None
        self.lang = lang

    def is_pdf(self, file_path: Union[str, Path]) -> bool:
        """Check if the given file path is a PDF."""
        return Path(file_path).suffix.lower() == ".pdf"

    def is_image(self, file_path: Union[str, Path]) -> bool:
        """Check if the given file path is a supported image."""
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_IMAGE_EXTS

    def extract_text_from_pdf_direct(self, pdf_path: Union[str, Path]) -> List[Dict[str, Any]]:
        """
        Attempts direct text stream extraction from digital PDFs using pypdfium2.
        Returns list of page data dictionaries if successful, otherwise empty list.
        """
        path = Path(pdf_path)
        if not HAS_PYPDFIUM2 or not path.exists():
            return []

        try:
            pdf = pdfium.PdfDocument(str(path))
            pages_data = []
            has_embedded_text = False

            for idx, page in enumerate(pdf, start=1):
                textpage = page.get_textpage()
                text = textpage.get_text_range()
                if text and len(text.strip()) > 30:
                    has_embedded_text = True
                pages_data.append({
                    "page_number": idx,
                    "width": int(page.get_size()[0]),
                    "height": int(page.get_size()[1]),
                    "applied_rotation_angle": 0,
                    "text": text.strip() if text else ""
                })

            pdf.close()
            return pages_data if has_embedded_text else []

        except Exception as e:
            logger.warning("Direct PDF text extraction notice for '%s': %s", path.name, e)
            return []

    def convert_pdf_to_images(self, pdf_path: Union[str, Path], dpi: int = 300) -> List[Image.Image]:
        """
        Converts PDF pages into high-resolution PIL Image objects.
        Uses pypdfium2, pdf2image, or system pdftoppm as fallbacks.
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")

        if HAS_PYPDFIUM2:
            try:
                pdf = pdfium.PdfDocument(str(path))
                images = [page.render(scale=3).to_pil() for page in pdf]
                pdf.close()
                return images
            except Exception as e:
                logger.warning("pypdfium2 conversion failed for '%s': %s. Trying fallback...", path.name, e)

        if HAS_PDF2IMAGE:
            try:
                return convert_from_path(str(path), dpi=dpi)
            except Exception as e:
                logger.warning("pdf2image conversion failed for '%s': %s. Trying fallback...", path.name, e)

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_dir_path = Path(tmp_dir)
                prefix = str(tmp_dir_path / "page")
                cmd = ["pdftoppm", "-png", "-r", str(dpi), str(path), prefix]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                generated_files = sorted(tmp_dir_path.glob("*.png"))
                images = []
                for img_file in generated_files:
                    with Image.open(img_file) as img:
                        images.append(img.copy())
                return images
        except Exception as e:
            raise RuntimeError(
                f"Failed to convert PDF to images. Please install poppler-utils or pypdfium2. Error: {e}"
            )

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocesses image for maximum OCR clarity:
        - Contrast enhancement + Sharpening
        """
        gray = image.convert('L')
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(1.8)
        sharpener = ImageEnhance.Sharpness(enhanced)
        return sharpener.enhance(1.5)

    def _score_text_quality(self, text: str) -> float:
        """Scores extracted text quality based on English alphanumeric density and structure."""
        if not text:
            return 0.0
        alnum_count = sum(1 for c in text if c.isalnum())
        space_count = sum(1 for c in text if c.isspace())
        colon_count = text.count(':')
        
        words = [w for w in text.split() if len(w) >= 2 and w.isalnum()]
        word_count = len(words)

        return (alnum_count * 1.0) + (space_count * 0.5) + (colon_count * 10.0) + (word_count * 5.0)

    def auto_orient_image(self, image: Image.Image) -> Tuple[Image.Image, int, str]:
        """
        Detects image orientation. If 0° delivers good quality text, returns immediately.
        Otherwise tests 90°, 180°, 270° to automatically detect rotated photos.
        """
        prep_0 = self.preprocess_image(image)
        text_0 = self._run_tesseract_ocr(prep_0)
        score_0 = self._score_text_quality(text_0)

        if score_0 >= 40.0:
            return image, 0, text_0

        best_angle = 0
        best_score = score_0
        best_text = text_0
        best_img = image

        for angle in [90, 180, 270]:
            rotated_img = image.rotate(angle, expand=True)
            prep_img = self.preprocess_image(rotated_img)
            text = self._run_tesseract_ocr(prep_img)
            score = self._score_text_quality(text)

            if score > best_score:
                best_score = score
                best_angle = angle
                best_text = text
                best_img = rotated_img

        if best_angle != 0:
            logger.info("Auto-rotated image by %d° clockwise for optimal text extraction.", best_angle)

        return best_img, best_angle, best_text

    def _run_tesseract_ocr(self, image: Image.Image) -> str:
        """Runs Tesseract OCR using English + Hindi language models."""
        config_arg = f'--tessdata-dir "{self.tessdata_dir}" --psm 3' if self.tessdata_dir else '--psm 3'

        if HAS_PYTESSERACT:
            try:
                text = pytesseract.image_to_string(image, lang=self.lang, config=config_arg)
                if text and len(text.strip()) > 5:
                    return text
            except Exception as e:
                logger.debug("Pytesseract execution exception: %s", e)

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)
                image.save(tmp_path, format="PNG")

            cmd = [self.tesseract_bin, str(tmp_path), "stdout", "-l", self.lang, "--psm", "3"]
            if self.tessdata_dir:
                cmd.extend(["--tessdata-dir", self.tessdata_dir])
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            text = result.stdout
        except subprocess.CalledProcessError as e:
            logger.warning("Tesseract subprocess failed: %s", e)
            text = ""
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

        return text

    def load_document(self, file_path: Union[str, Path]) -> List[Image.Image]:
        """
        Loads document from path (Image or PDF) and returns list of page images.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if self.is_pdf(path):
            logger.info("Converting PDF '%s' to images...", path.name)
            return self.convert_pdf_to_images(path)
        elif self.is_image(path):
            logger.info("Loading image '%s'...", path.name)
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            return [img]
        else:
            raise ValueError(
                f"Unsupported file format: {path}. Supported formats: PDF, {', '.join(self.SUPPORTED_IMAGE_EXTS)}"
            )

    def convert_image_to_base64(self, image: Image.Image, format: str = "PNG") -> str:
        """Converts PIL Image to base64 encoded string."""
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def process_images_base64(self, file_path: Union[str, Path]) -> List[str]:
        """Loads document file and converts all pages to base64 image strings without running Tesseract OCR."""
        images = self.load_document(file_path)
        return [self.convert_image_to_base64(img) for img in images]

    def process(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Main entry point: accepts doc (image or pdf).
        If PDF, attempts direct text stream extraction first.
        If scanned or image, auto-orients, preprocesses image, performs OCR.
        """
        path = Path(file_path)
        if self.is_pdf(path):
            direct_pages = self.extract_text_from_pdf_direct(path)
            if direct_pages:
                logger.info("Extracted text directly from digital PDF '%s' (%d pages).", path.name, len(direct_pages))
                full_text_parts = [p["text"] for p in direct_pages if p["text"]]
                return {
                    "source_file": str(path.resolve()),
                    "file_type": "pdf",
                    "total_pages": len(direct_pages),
                    "ocr_language": self.lang,
                    "pages": direct_pages,
                    "full_text": "\n\n".join(full_text_parts)
                }

        images = self.load_document(path)
        pages_data = []
        full_text_parts = []

        for idx, img in enumerate(images, start=1):
            logger.info("Performing OCR on page %d/%d...", idx, len(images))
            oriented_img, rotation_angle, ocr_text = self.auto_orient_image(img)
            pages_data.append({
                "page_number": idx,
                "width": img.width,
                "height": img.height,
                "applied_rotation_angle": rotation_angle,
                "text": ocr_text.strip()
            })
            full_text_parts.append(ocr_text.strip())

        return {
            "source_file": str(path.resolve()),
            "file_type": "pdf" if self.is_pdf(path) else "image",
            "total_pages": len(images),
            "ocr_language": self.lang,
            "pages": pages_data,
            "full_text": "\n\n".join(full_text_parts)
        }
