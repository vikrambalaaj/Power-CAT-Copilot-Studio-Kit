import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class SACSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    sac_tenant_url: str = "https://your-sac-tenant.eu10.sapanalytics.cloud"
    sac_auth_mode: str = "oauth"
    sac_token_url: str = "https://your-sac-auth.authentication.eu10.hana.ondemand.com/oauth/token"
    sac_client_id: str = ""
    sac_client_secret: str = ""

    port: int = 8084
    mcp_api_key: str = "velora-sac-secret-2026"
    allow_anonymous: bool = True
    allowed_hosts: str = "*"
    cors_origins: str = "*"
    log_level: str = "INFO"

    cache_enabled: bool = True
    cache_ttl_seconds: int = 120
    cache_max_entries: int = 512
    oauth_token_cache_skew_seconds: int = 30
    public_base_url: str = "https://sac-analytics-mcp-server.cfapps.eu10-005.hana.ondemand.com"


settings = SACSettings()
