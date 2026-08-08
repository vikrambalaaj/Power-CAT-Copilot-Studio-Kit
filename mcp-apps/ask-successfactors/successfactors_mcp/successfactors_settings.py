"""Configuration settings for the SAP SuccessFactors MCP server."""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class SuccessFactorsSettings(BaseSettings):
    # Secrets and tenant identifiers intentionally have no usable defaults.
    sf_api_url: str = ""
    sf_company_id: str = ""
    sf_username: str = ""
    sf_password: str = ""

    # Optional, tenant-specific filter used to calculate the aggregate KPI.
    # Example: customString10 eq 'Emirati'
    sf_emirati_filter: str = ""
    sf_emiratisation_target: float = 40.0

    port: int = 8082
    cors_origins: str = ""
    allowed_hosts: str = "localhost:*,127.0.0.1:*"
    allowed_origins: str = ""
    mcp_api_key: str = ""
    allow_anonymous: bool = False
    enable_mutating_tools: bool = False
    enable_widget: bool = False
    log_level: str = "INFO"
    cache_enabled: bool = True
    cache_ttl_seconds: int = 120
    cache_max_entries: int = 512

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


from typing import Optional

_settings: Optional[SuccessFactorsSettings] = None


def get_settings() -> SuccessFactorsSettings:
    global _settings
    if _settings is None:
        _settings = SuccessFactorsSettings()
    return _settings
