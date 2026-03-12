"""Application configuration loaded from environment variables."""

from pydantic import model_validator
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """All settings are loaded from environment variables or .env file."""

    # Application
    app_name: str = "Echo 2.0"
    app_version: str = "1.0.0"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # Supabase
    supabase_url: str
    supabase_key: str

    # Microsoft Entra ID (SSO)
    entra_client_id: str
    entra_client_secret: str
    entra_tenant_id: str
    entra_redirect_uri: str = "http://localhost:8000/auth/callback"
    entra_authority: str = ""

    # App URL
    base_url: str = "http://localhost:8000"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @model_validator(mode="after")
    def set_entra_authority(self):
        if not self.entra_authority:
            self.entra_authority = (
                f"https://login.microsoftonline.com/{self.entra_tenant_id}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
