from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Neo4j Configuration
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"
    
    # PostgreSQL Configuration
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "codebase_analysis"
    postgres_user: str = "postgres"
    postgres_password: str = "password123"
    postgres_url: str = ""
    
    # Redis Configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    # OpenAI Configuration (env: OPENAI_API_KEY, OPENAI_MODEL, OPENAI_MODEL_FALLBACKS)
    openai_api_key: str = ""
    openai_model: str = "gpt-5.3"
    # Comma-separated; only used if primary fails. Default empty so all chat uses OPENAI_MODEL only.
    openai_model_fallbacks: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_base_url: str = "https://api.openai.com/v1"
    
    # GitHub Configuration
    github_token: str = ""
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    secret_key: str = "change-me-in-production"
    api_key: str = "dev-local-key"
    allowed_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]
    
    # File Storage
    upload_dir: str = "./uploads"
    repositories_dir: str = "./repositories"
    max_upload_size: int = 100 * 1024 * 1024  # 100MB
    # 1 = shallow clone (much faster UI → “Running”). 0 = full history (slower; temporal/git views see more history).
    git_clone_depth: int = 1
    # Temporal analysis deepens shallow clones automatically. 0 = full unshallow.
    temporal_fetch_depth: int = 200
    # Temporal UI: default sample sizes (fast load). API query params can override.
    temporal_sample_max_commits: int = 10
    temporal_sample_max_prs: int = 10
    temporal_sample_max_comments: int = 10
    
    # Agent Configuration
    agent_max_iterations: int = 100
    agent_timeout: int = 3600  # 1 hour
    # Documentation agent: one LLM call per service — use parallel workers to overlap network latency.
    # Set to 0 to force sequential (e.g. debugging). Env: DOCUMENTATION_PARALLEL_WORKERS
    documentation_parallel_workers: int = 8
    # Faster / cheaper model for documentation generation (formulaic JSON output).
    # Falls back to OPENAI_MODEL when blank. Env: DOCUMENTATION_MODEL
    documentation_model: str = "gpt-4.1-mini"
    # Hard cap on services that may use LLM docs in one run (top-priority services only).
    # 0 means no cap. Env: DOCUMENTATION_MAX_LLM_SERVICES
    documentation_max_llm_services: int = 24
    # Parse fallback file cap when code_elements miss a service path.
    # Lower values reduce documentation stage latency on large repos.
    documentation_parse_fallback_max_files: int = 40
    # Max completion tokens per service doc JSON (lower = faster / cheaper; higher = longer markdown).
    documentation_max_tokens: int = 2200
    # Timeout per documentation LLM request to avoid long tail latency. Env: DOCUMENTATION_LLM_TIMEOUT_SEC
    documentation_llm_timeout_sec: int = 30
    # Skip expensive LLM docs for tiny / low-signal services and use structural docs immediately.
    documentation_llm_min_signal: int = 4
    # Codebase chat: cap embedding rerank candidates to avoid many embedding API calls on large inventories.
    chat_rerank_candidate_cap: int = 12
    # Code browser parses up to N source files into code_elements (order is filesystem-dependent).
    # Keep high enough that top-level packages (api/, backend/) are not starved by the cap.
    code_browser_max_files: int = 600
    # When True, workflow stops at the first pending human-review checkpoint (may strand progress < 100%).
    # Default False so analysis runs unattended; enable for interactive review flows.
    orchestrator_pause_on_checkpoints: bool = False
    
    # Rate Limiting
    rate_limit_per_minute: int = 60
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text
    
    class Config:
        env_file = (".env", "backend/.env")
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
