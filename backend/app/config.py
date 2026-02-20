from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "FluxRules"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    DATABASE_URL: str = "sqlite:///./rule_engine.db"
    
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    WORKER_CONCURRENCY: int = 4
    
    # Engine settings
    USE_OPTIMIZED_ENGINE: bool = True  # Set to False to use simple engine
    RULE_CACHE_TTL: int = 300  # Cache TTL in seconds (5 minutes)
    RULE_LOCAL_CACHE_TTL: int = 60  # Local cache TTL in seconds
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()