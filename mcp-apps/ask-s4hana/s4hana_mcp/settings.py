"""Configuration for the S/4HANA finance MCP server."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    s4_api_url: str = ""
    s4_auth_mode: str = "basic"
    s4_token_url: str = ""
    s4_client_id: str = ""
    s4_client_secret: str = ""
    s4_username: str = ""
    s4_password: str = ""
    s4_sap_client: str = "100"
    s4_ar_entity: str = "ARageingData"
    s4_ap_entity: str = "APageingData"
    s4_budget_api_url: str = "https://fioriqas.velora.ae/sap/opu/odata4/sap/zfi_sbn_budget_consm_srv/srvd_a2x/sap/zfi_sdf_budget_consm/0001"
    s4_budget_entity: str = "BudgetConsumption"
    s4_pl_api_url: str = ""
    s4_pl_entity: str = ""
    port: int = 8083
    mcp_api_key: str = ""
    allow_anonymous: bool = True
    allowed_hosts: str = "localhost:*,127.0.0.1:*,*"
    allowed_origins: str = ""
    cors_origins: str = "*"
    log_level: str = "INFO"
    cache_enabled: bool = True
    cache_ttl_seconds: int = 60
    cache_max_entries: int = 512
    oauth_token_cache_skew_seconds: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

