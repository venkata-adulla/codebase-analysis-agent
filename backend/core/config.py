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
    
    # Qdrant Configuration
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    
    # Redis Configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    # OpenAI Configuration
    openai_api_key: str = ""
    openai_model: str = "gpt-5.3"
    openai_model_fallbacks: str = "gpt-4o-mini,gpt-4.1-mini"
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
    
    # Agent Configuration
    agent_max_iterations: int = 100
    agent_timeout: int = 3600  # 1 hour
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
