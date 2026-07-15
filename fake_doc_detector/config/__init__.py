"""Configuration settings for the detection pipeline"""

import os
from pathlib import Path
from typing import Dict, Any

# Load variables from .env file if it exists
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    with open(_env_path, "r") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                os.environ[_key.strip()] = _val.strip("'\"")



class Config:
    """Configuration class for the fake document detection system"""
    
    # Paths
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DATA_DIR = PROJECT_ROOT / "data"
    DOCUMENTS_DIR = DATA_DIR / "sample_documents"
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Document types
    DOCUMENT_TYPES = ["aadhar", "pan", "ration_card", "voter_id"]
    
    # Detection parameters (to be filled later)
    DETECTION_THRESHOLD = 0.8
    BATCH_SIZE = 32
    
    # Cryptographic Key Paths
    UIDAI_PUBLIC_KEY_PATH = os.getenv("UIDAI_PUBLIC_KEY_PATH", None)
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "project_root": str(cls.PROJECT_ROOT),
            "data_dir": str(cls.DATA_DIR),
            "documents_dir": str(cls.DOCUMENTS_DIR),
            "log_level": cls.LOG_LEVEL,
            "document_types": cls.DOCUMENT_TYPES,
            "detection_threshold": cls.DETECTION_THRESHOLD,
            "batch_size": cls.BATCH_SIZE,
            "uidai_public_key_path": cls.UIDAI_PUBLIC_KEY_PATH,
        }


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False


def get_config(env: str = None) -> Config:
    """
    Get configuration based on environment.
    
    Args:
        env: Environment name (development, testing, production)
    
    Returns:
        Configuration object
    """
    if env is None:
        env = os.getenv("ENVIRONMENT", "development")
    
    config_map = {
        "development": DevelopmentConfig,
        "testing": TestingConfig,
        "production": ProductionConfig,
    }
    
    return config_map.get(env, DevelopmentConfig)()
