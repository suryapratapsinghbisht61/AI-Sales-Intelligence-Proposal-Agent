import json
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://salespilot:salespilot@localhost:5432/salespilot"
    frontend_origin: str = "http://localhost:3000"
    session_days: int = 14
    cookie_secure: bool = False

    # "provider:model" strings for LangChain's init_chat_model / init_embeddings; empty = not configured
    chat_model: str = ""
    fast_model: str = ""  # cheaper model for classification/extraction; falls back to chat_model
    embedding_model: str = ""
    embedding_dim: int = 768  # fixed by the DB migration; providers are asked for this many dims
    llm_timeout_s: int = 60
    llm_max_retries: int = 2
    max_output_tokens: int = 2000
    # JSON {"provider:model": [usd_per_mtok_in, usd_per_mtok_out]}; empty = cost not estimated
    model_prices: str = ""
    org_monthly_token_budget: int = 2_000_000

    storage_backend: str = "local"  # local | s3
    storage_dir: str = "./data/uploads"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    max_upload_mb: int = 20

    chunk_size: int = 1200
    chunk_overlap: int = 150
    research_cache_days: int = 30
    rate_limit_per_minute: int = 60

    @property
    def prices(self) -> dict:
        return json.loads(self.model_prices) if self.model_prices else {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
