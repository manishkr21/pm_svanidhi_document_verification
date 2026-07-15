import subprocess
import tempfile
import logging
import io
import atexit
from pathlib import Path
from typing import List, Tuple, Generator, Dict
from contextlib import contextmanager
from PIL import Image

logger = logging.getLogger(__name__)

# Global cache for PDF contents:
# maps resolved absolute PDF path to tuple: (selectable_text, list_of_temp_image_paths, TemporaryDirectory_object)
_PDF_CACHE: Dict[str, Tuple[str, List[Path], tempfile.TemporaryDirectory]] = {}

def cleanup_pdf_cache() -> None:
    """Clean up all cached temporary directories and files."""
    cached_count = len(_PDF_CACHE)
    if cached_count > 0:
        logger.info(f"Cleaning up {cached_count} PDF cache directories...")
    for pdf_path, (_, _, temp_dir) in list(_PDF_CACHE.items()):
        try:
            temp_dir.cleanup()
            logger.debug(f"Cleaned up PDF cache directory for: {pdf_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up cached PDF directory for {pdf_path}: {e}")
    _PDF_CACHE.clear()

atexit.register(cleanup_pdf_cache)

@contextmanager
def extract_pdf_contents(pdf_path: str, dpi: int = 300) -> Generator[Tuple[str, List[Path]], None, None]:
    """
    Extract text and images from a PDF file. Caches results to avoid redundant rendering/extraction.
    
    Yields a tuple:
        (selectable_text, list_of_image_paths)
        
    - selectable_text: Direct text extracted from the PDF pages using PyPDF2.
    - list_of_image_paths: Paths to temporary PNG images representing either:
        a) Rendered pages of the PDF (via pdftoppm)
        b) Extracted embedded images from the PDF (fallback via PyPDF2 if pdftoppm is missing)
    """
    pdf_path_abs = str(Path(pdf_path).resolve())
    
    # Check if cache hits
    if pdf_path_abs in _PDF_CACHE:
        selectable_text, image_paths, _ = _PDF_CACHE[pdf_path_abs]
        logger.debug(f"PDF extraction cache hit for: {pdf_path_abs}")
        yield selectable_text, image_paths
        return
        
    logger.debug(f"PDF extraction cache miss. Rendering/extracting contents for: {pdf_path_abs}")
    
    # If not in cache, create a new TemporaryDirectory
    temp_dir = tempfile.TemporaryDirectory()
    try:
        temp_dir_path = Path(temp_dir.name)
        selectable_text = ""
        image_paths = []
        
        # 1. Try to extract direct selectable text using PyPDF2
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text_parts = []
                for page in reader.pages:
                    txt = page.extract_text()
                    if txt:
                        text_parts.append(txt)
                selectable_text = "\n".join(text_parts)
        except Exception as e:
            logger.warning(f"Failed to extract selectable text using PyPDF2: {e}")
            
        # 2. Try to render PDF pages using pdftoppm
        pdftoppm_success = False
        try:
            cmd = ["pdftoppm", "-png", "-r", str(dpi), pdf_path, str(temp_dir_path / "page")]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            image_paths = sorted(temp_dir_path.glob("page-*.png"))
            pdftoppm_success = True
            logger.debug(f"Successfully rendered PDF pages using pdftoppm: {len(image_paths)} pages")
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            logger.info(f"pdftoppm not available or failed: {e}. Falling back to PyPDF2 image extraction.")
            
        # 3. Fallback: Extract embedded XObject images using PyPDF2
        if not pdftoppm_success:
            try:
                import PyPDF2
                from PyPDF2.filters import _xobj_to_image
                
                with open(pdf_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    img_counter = 0
                    for page_idx, page in enumerate(reader.pages):
                        if "/Resources" in page and "/XObject" in page["/Resources"]:
                            x_object = page["/Resources"]["/XObject"]
                            for obj_name in x_object:
                                obj = x_object[obj_name]
                                if obj.get('/Subtype') == '/Image':
                                    try:
                                        extension, byte_stream = _xobj_to_image(obj)
                                        img = Image.open(io.BytesIO(byte_stream))
                                        if img.mode not in ("1", "L", "RGB", "RGBA"):
                                            img = img.convert("RGB")
                                        
                                        img_path = temp_dir_path / f"extracted_{page_idx+1}_{img_counter}.png"
                                        img.save(img_path, format="PNG")
                                        image_paths.append(img_path)
                                        img_counter += 1
                                    except Exception as img_err:
                                        logger.debug(f"Skipped image {obj_name} due to extraction error: {img_err}")
                logger.debug(f"Successfully extracted embedded images using PyPDF2: {len(image_paths)} images")
            except Exception as e:
                logger.error(f"Fallback PyPDF2 image extraction failed: {e}")
                
        # Store in cache
        _PDF_CACHE[pdf_path_abs] = (selectable_text, image_paths, temp_dir)
        yield selectable_text, image_paths
        
    except Exception:
        temp_dir.cleanup()
        raise
