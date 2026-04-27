"""Application settings loaded from environment variables or .env file."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """LacquerTutor configuration.

    Values are loaded from environment variables prefixed with LACQUERTUTOR_
    or from a .env file in the project root.
    """

    model_config = SettingsConfigDict(
        env_prefix="LACQUERTUTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # LLM connection
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen-plus"
    llm_temperature: float = 0.0

    # Data paths
    benchmark_dir: str = Field(
        default="../benchmark",
        description="Path to benchmark directory (taskset + evidence cards)",
    )

    # Pipeline parameters
    max_questions: int = Field(default=6, ge=1, le=20)
    evidence_top_k: int = Field(default=4, ge=1, le=10)
    max_revisions: int = Field(default=2, ge=0, le=5)
    max_turns: int = Field(default=80, ge=10, le=200, description="Max agent turns per session")
    max_cost_usd: float = Field(default=5.0, description="Max cost in USD per session (circuit breaker)")
    memory_session_window: int = Field(default=24, ge=1, le=100, description="How many past sessions to scan for memory")
    memory_profile_limit: int = Field(default=4, ge=0, le=10, description="Max remembered preference items to inject")
    memory_recall_limit: int = Field(default=3, ge=0, le=10, description="Max similar sessions to recall")
    memory_playbook_limit: int = Field(default=2, ge=0, le=10, description="Max learned playbooks to inject")
    mem0_data_dir: str = Field(default=".data/mem0", description="Persistent directory for Mem0 local storage")
    mem0_collection: str = Field(default="lacquertutor_memories")
    mem0_top_k: int = Field(default=5, ge=1, le=20)

    # Retrieval / Qdrant
    qdrant_url: str = Field(default="", description="Qdrant server URL. Empty = in-memory mode.")
    qdrant_collection: str = Field(default="lacquertutor_evidence")
    embedding_model: str = Field(default="text-embedding-v3")
    rerank_model: str = Field(default="gte-rerank-v2")
    rag_index_dir: str = Field(default=".data/rag")
    rag_collection: str = Field(default="lacquertutor_kb_segments")
    rag_dense_top_k: int = Field(default=24, ge=4, le=100)
    rag_candidate_pool: int = Field(default=12, ge=4, le=50)
    rag_final_top_k: int = Field(default=4, ge=1, le=10)
    rag_warm_on_start: bool = Field(default=False)

    # Observability
    tracing_enabled: bool = Field(default=True)
    cost_limit_per_session: float = Field(default=5.0, description="Max cost in USD per session")

    # Storage
    database_url: str = Field(default="sqlite+aiosqlite:///lacquertutor.db")
    session_db_path: str = Field(default="lacquertutor_web.db")
    upload_dir: str = Field(default=".data/uploads")
    max_upload_size_mb: int = Field(default=5, ge=1, le=50)
    max_uploads_per_session: int = Field(default=20, ge=1, le=200)
    auth_secret_key: str = Field(
        default="lacquertutor-dev-secret",
        description="Secret key for signing lightweight auth cookies",
    )
    auth_cookie_name: str = Field(default="lacquertutor_session")
    auth_session_max_age_sec: int = Field(default=60 * 60 * 24 * 14, ge=3600)

    @property
    def benchmark_path(self) -> Path:
        """Resolve benchmark directory to absolute path."""
        p = Path(self.benchmark_dir)
        if not p.is_absolute():
            # Resolve relative to the lacquertutor project root
            p = Path(__file__).resolve().parent.parent.parent / self.benchmark_dir
        return p.resolve()

    @property
    def taskset_path(self) -> Path:
        return self.benchmark_path / "taskset_v0.json"

    @property
    def evidence_cards_path(self) -> Path:
        return self.benchmark_path / "evidence_cards_v0.json"
