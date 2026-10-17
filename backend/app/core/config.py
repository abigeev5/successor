from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root .env (local runs from backend/); inside docker the variables come from compose.
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Application settings, read from environment / .env (see .env.example)."""

    model_config = SettingsConfigDict(env_file=(_ROOT_ENV, ".env"), env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://preemnik:preemnik@localhost:5432/preemnik"

    # Auth
    jwt_secret: str = "change-me"
    jwt_ttl_hours: int = 12
    cookie_secure: bool = False

    # Files
    storage_dir: Path = Path("/data")

    # Demo stand: shows the banner and demo accounts on the login page
    demo_mode: bool = True

    # LLM
    llm_provider: Literal["openai_compatible", "gigachat", "fake"] = "fake"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_judge_model: str = ""
    llm_timeout_s: float = 60.0
    llm_json_mode: Literal["json_schema", "json_object", "none"] = "json_schema"
    gigachat_credentials: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"

    # Embeddings
    embeddings_provider: Literal["sentence_transformers", "openai_compatible", "fake"] = "fake"
    embeddings_model: str = "BAAI/bge-m3"
    embeddings_base_url: str = ""
    embeddings_api_key: str = ""
    embeddings_device: str = "cpu"
    embeddings_dim: int = 1024

    # Speech recognition
    asr_provider: Literal["faster_whisper", "gigaam", "fake"] = "fake"
    asr_model: str = "small"  # D-031; a local directory path also works (offline contour)
    asr_download_root: str = ""  # where faster-whisper keeps downloaded models; empty = HF cache
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"

    # Vision
    vlm_enabled: bool = False
    vlm_base_url: str = ""
    vlm_model: str = ""
    # Real OCR by default: without it screenshots cannot be checked for personal data (D-058).
    ocr_engine: Literal["easyocr", "tesseract", "fake"] = "tesseract"

    # Assistant search (SPEC 7.8). Thresholds are calibrated by `make eval` (D-047).
    rag_min_similarity: float = 0.45
    rag_min_text_coverage: float = 0.6  # share of question words in one chunk that counts as a text match
    rag_top_k: int = 20
    rag_top_chunks: int = 8
    rag_max_cards: int = 5

    # Screen recordings (SPEC 7.6)
    recording_max_mb: int = 1024
    recording_max_minutes: int = 30

    # Manager dashboard: risk level boundaries (SPEC 7.9; the team may change them, SPEC 17.5)
    risk_high: float = 0.35
    risk_medium: float = 0.15

    # Privacy
    offline_mode: bool = False
    retention_days_raw_media: int = 180
    retention_check_interval_s: float = 60 * 60  # how often the worker looks for expired raw media

    # Worker
    worker_poll_interval_s: float = 1.0
    job_max_attempts: int = 3
    job_backoff_base_s: float = 5.0
    job_stale_after_s: float = 30 * 60

    @property
    def effective_judge_model(self) -> str:
        return self.llm_judge_model or self.llm_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
