"""Configuration settings for the SAP SuccessFactors MCP server."""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class SuccessFactorsSettings(BaseSettings):
    # Secrets and tenant identifiers intentionally have no usable defaults.
    sf_api_url: str = ""
    sf_company_id: str = ""
    sf_username: str = ""
    sf_password: str = ""

    # Legacy tenant-specific filter retained for backwards compatibility. New
    # deployments should configure the explicit nationality mapping below.
    sf_emirati_filter: str = ""
    sf_emiratisation_target: float = 40.0
    sf_nationality_entity: str = "PerPersonal"
    sf_nationality_person_id_field: str = "personIdExternal"
    sf_nationality_field: str = "nationality"
    sf_uae_nationality_codes: str = "ARE"
    sf_active_user_statuses: str = "t"
    sf_voluntary_event_reasons: str = ""
    sf_involuntary_event_reasons: str = ""
    sf_metric_rule_version: str = "velora-workforce-v2"
    sf_small_group_threshold: int = 5

    port: int = 8082
    cors_origins: str = ""
    allowed_hosts: str = "localhost:*,127.0.0.1:*"
    allowed_origins: str = ""
    mcp_api_key: str = ""
    allow_anonymous: bool = False
    enable_mutating_tools: bool = False
    enable_personal_info_tool: bool = False
    enable_widget: bool = False
    log_level: str = "INFO"
    cache_enabled: bool = True
    cache_ttl_seconds: int = 120
    cache_max_entries: int = 512
    aggregate_cache_ttl_seconds: int = 900
    aggregate_cache_max_entries: int = 128
    public_base_url: str = ""

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
