import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv

# Load .env from the backend root directory
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


class Settings:
    """Application settings, loaded from environment variables.

    Provides a singleton via get_settings() so that the .env file is
    parsed exactly once across the whole application.
    """

    def __init__(self) -> None:
        self.ollama_base_url: str = os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        self.embedding_model: str = os.environ.get("EMBEDDING_MODEL", "bge-m3")
        self.llm_model: str = os.environ.get("LLM_MODEL", "qwen2.5:7b")
        self.chroma_data_dir: str = os.environ.get(
            "CHROMA_DATA_DIR", "./data/chroma"
        )
        self.upload_dir: str = os.environ.get("UPLOAD_DIR", "./data/uploads")

        # Resolve relative paths against the backend root
        _backend_root = Path(__file__).resolve().parent.parent
        if not Path(self.chroma_data_dir).is_absolute():
            self.chroma_data_dir = str(_backend_root / self.chroma_data_dir)
        if not Path(self.upload_dir).is_absolute():
            self.upload_dir = str(_backend_root / self.upload_dir)


@lru_cache()
def get_settings() -> Settings:
    """Return the cached, single Settings instance."""
    return Settings()
