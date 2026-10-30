"""
Application Configuration.

Loads settings from environment variables using pydantic-settings.
All sensitive values are read from .env and validated at startup.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration class.
    Values are loaded from .env file and environment variables.
    Environment variables take precedence over .env values.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra env vars not defined here
    )

    # --- Application ---
    APP_NAME: str = "Syragent - AI Agent Service Management Platform"
    APP_ENV: str = "development"
    SECRET_KEY: str  # Required — no default for security
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Database (Supabase PostgreSQL + pgvector) ---
    DATABASE_URL: str  # Required — must point to Supabase

    # --- Encryption (Fernet symmetric key) ---
    ENCRYPTION_KEY: str  # Required — generate with Fernet.generate_key()

    # --- Platform Managed AI Keys (Syragent Managed Infrastructure) ---
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""

    from pydantic import field_validator

    @field_validator(
        "DATABASE_URL",
        "SECRET_KEY",
        "ENCRYPTION_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        mode="before",
    )
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


# Singleton instance — import this everywhere
settings = Settings()

