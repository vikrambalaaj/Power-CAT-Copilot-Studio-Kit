"""Configuration for the S/4HANA finance MCP server."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    s4_api_url: str = "https://fiori.velora.ae/sap/opu/odata4/sap/zfi_sbn_ageingdata_srv/srvd_a2x/sap/zfi_sdf_ageingdata_srv/0001"
    s4_auth_mode: str = "basic"
    s4_token_url: str = ""
    s4_client_id: str = ""
    s4_client_secret: str = ""
    s4_username: str = "API_USER"
    s4_password: str = ""
    s4_username_secret_ref: str = ""
    s4_password_secret_ref: str = ""
    mcp_api_key_secret_ref: str = ""
    s4_sap_client: str = "100"
    s4_verify_tls: bool = True
    s4_ca_bundle: str = ""
    
    executing_identity: str = "velora-s4-finance-reader"
    authorization_model: str = "MAKER_SERVICE_CREDENTIAL"

    # Three approved reports in scope + GLDetails:
    s4_ar_entity: str = "ARageingData"
    s4_ap_entity: str = "APageingData"
    s4_budget_transfer_entity: str = ""
    s4_budget_consumption_entity: str = "BudgetConsumSummary"
    s4_pl_entity: str = "GLDetails"

    # Legacy / Master Data entity configuration
    s4_budget_api_url: str = ""
    s4_budget_entity: str = "BudgetConsumSummary"
    s4_customer_api_url: str = ""
    s4_customer_entity: str = "CustomerMaster"
    s4_costcenter_api_url: str = ""
    s4_costcenter_entity: str = "CostCenterMaster"
    s4_profitcenter_api_url: str = ""
    s4_profitcenter_entity: str = "ProfitCenterMaster"

    # Environment & Governance settings
    s4_environment_label: str = "Production"
    s4_report_timezone: str = "Asia/Dubai"
    s4_report_max_rows: int = 1000
    s4_report_max_pages: int = 50
    s4_total_timeout_seconds: float = 60.0

    port: int = 8083
    mcp_api_key: str = ""
    allow_anonymous: bool = False
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


S4Settings = Settings

