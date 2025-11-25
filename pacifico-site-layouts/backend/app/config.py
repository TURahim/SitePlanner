"""
Application configuration from environment variables.
"""
import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = "Pacifico Site Layouts API"
    debug: bool = False
    
    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "pacifico_layouts"
    db_username: str = "postgres"
    db_password: str = ""
    
    # AWS
    aws_region: str = "us-east-1"
    s3_uploads_bucket: str = ""
    s3_outputs_bucket: str = ""
    
    # Cognito
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""
    
    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    
    @property
    def database_url(self) -> str:
        """Construct async database URL for SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
    
    @property
    def database_url_sync(self) -> str:
        """Construct sync database URL for Alembic migrations."""
        return (
            f"postgresql+psycopg://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

