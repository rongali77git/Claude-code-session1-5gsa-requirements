from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="config/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Corporate LLM ────────────────────────────────────────────
    corp_llm_endpoint: str
    corp_llm_api_key: str
    corp_llm_model_name: str = "gpt-4"
    corp_llm_max_tokens: int = 2048
    corp_llm_temperature: float = 0.1
    corp_llm_timeout_seconds: int = 60

    # ── Embeddings ────────────────────────────────────────────────
    embedding_model: str = "BAAI/bge-large-en-v1.5"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32

    # ── Neo4j ─────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str
    neo4j_database: str = "5gsa"

    # ── Vector Store ──────────────────────────────────────────────
    vector_store_backend: Literal["chroma", "pgvector"] = "chroma"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "vectordb"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    chroma_persist_dir: str = "./data/chroma"

    # ── Ingestion ─────────────────────────────────────────────────
    docs_input_dir: str = "./data/docs"
    chunk_size: int = 512
    chunk_overlap: int = 64

    # ── App ───────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"


# Singleton
settings = Settings()
