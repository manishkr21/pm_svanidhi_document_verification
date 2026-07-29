"""
config.py

Centralized configuration management and logging setup for PMS-Extractor.
Handles environment variables, default settings, path resolution using pathlib.Path,
and standardized application logging.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Set

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))

# Configure Application Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("pms_extractor")

# Application Settings
BASE_DIR: Path = Path(__file__).parent.resolve()
LOCAL_TESSDATA: Path = BASE_DIR / "tessdata"
TESSDATA_DIR: Optional[Path] = LOCAL_TESSDATA if LOCAL_TESSDATA.exists() else None

if TESSDATA_DIR:
    os.environ["TESSDATA_PREFIX"] = str(TESSDATA_DIR)

DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "claude-fable-5")
DEFAULT_PORT: int = int(os.getenv("PORT", "8005"))
API_TIMEOUT: int = int(os.getenv("API_TIMEOUT", "60"))

SUPPORTED_IMAGE_EXTS: Set[str] = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"}


def get_api_key() -> Optional[str]:
    """Retrieves API key from environment."""
    return os.getenv("ANTHROPIC_API_KEY")
