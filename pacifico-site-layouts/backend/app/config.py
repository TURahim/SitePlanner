"""
Application configuration from environment variables.
"""
import os
from functools import lru_cache
from typing import Optional
from urllib.parse import quote_plus

from pydantic import field_validator
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
    
    # SQS (Phase C: Async job processing)
    sqs_queue_url: str = ""  # Layout jobs queue URL
    sqs_queue_name: str = "pacifico-layouts-dev-layout-jobs"  # Fallback name if URL not provided
    enable_async_layout_generation: bool = False  # Enable async job queuing (C-03)
    
    # Cognito
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""
    
    # CORS - allowed origins for cross-origin requests
    cors_origins: list[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev server
        "https://microgridcalculator.tahmeedrahim.com",  # Production frontend
        "https://d178b416db7o5o.cloudfront.net",  # CloudFront distribution
    ]
    
    # Layout Generation
    # Terrain-aware layout generation is enabled by default.
    # Set USE_TERRAIN=false to fall back to the dummy generator for debugging.
    use_terrain: bool = True
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from comma-separated string or list."""
        if isinstance(v, str):
            # Handle comma-separated string from environment variable
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    @property
    def database_url(self) -> str:
        """Construct async database URL for SQLAlchemy."""
        # URL-encode the password to handle special characters
        encoded_password = quote_plus(self.db_password)
        return (
            f"postgresql+asyncpg://{self.db_username}:{encoded_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
    
    @property
    def database_url_sync(self) -> str:
        """Construct sync database URL for Alembic migrations."""
        # URL-encode the password to handle special characters
        encoded_password = quote_plus(self.db_password)
        return (
            f"postgresql+psycopg://{self.db_username}:{encoded_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

