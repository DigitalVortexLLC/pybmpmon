"""Application configuration using Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # BMP Listener
    bmp_listen_host: str = Field(default="0.0.0.0", description="BMP listener host")
    bmp_listen_port: int = Field(
        default=11019, ge=1, le=65535, description="BMP listener port"
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Database
    db_host: str = Field(default="localhost", description="Database host")
    db_port: int = Field(default=5432, ge=1, le=65535, description="Database port")
    db_user: str = Field(default="bmpmon", description="Database user")
    db_password: str = Field(default="", description="Database password")
    db_name: str = Field(default="bmpmon", description="Database name")
    db_pool_min_size: int = Field(
        default=5, ge=1, le=100, description="Database pool minimum size"
    )
    db_pool_max_size: int = Field(
        default=10, ge=1, le=100, description="Database pool maximum size"
    )

    # Sentry (optional)
    sentry_dsn: str | None = Field(
        default=None, description="Sentry DSN (leave empty to disable)"
    )
    sentry_environment: str = Field(
        default="development", description="Sentry environment"
    )
    sentry_traces_sample_rate: float = Field(
        default=0.1, ge=0.0, le=1.0, description="Sentry traces sample rate"
    )

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


# Global settings instance
settings = Settings()
