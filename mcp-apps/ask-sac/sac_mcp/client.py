import time
import httpx
from typing import Any, Dict, List, Optional
from sac_mcp.settings import settings
from sac_mcp.cache import cache


class SACAuthenticationError(RuntimeError):
    """Raised when SAC OAuth authentication fails."""
    pass


class SACClient:
    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    async def get_token(self) -> Optional[str]:
        if not settings.sac_client_id or not settings.sac_client_secret:
            return None
        if self._token and time.time() < (self._token_expires_at - settings.oauth_token_cache_skew_seconds):
            return self._token

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    settings.sac_token_url,
                    data={"grant_type": "client_credentials"},
                    auth=(settings.sac_client_id, settings.sac_client_secret),
                )
                if res.status_code == 200:
                    data = res.json()
                    self._token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                    self._token_expires_at = time.time() + expires_in
                    return self._token
        except Exception:
            pass
        return None

    async def get_executive_kpis(self, domain: str = "FINANCE") -> Dict[str, Any]:
        cache_key = f"sac_kpi_{domain.upper()}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        token = await self.get_token()
        if not token:
            if not settings.demo_mode:
                raise RuntimeError("SAC live integration is not configured")
            data = {
                "source": "Synthetic demonstration data",
                "isDemoData": True,
                "domain": domain.upper(),
                "as_of": "2026-08-15T00:00:00Z",
                "audit": {
                    "executingIdentity": settings.executing_identity,
                    "authorizationModel": settings.authorization_model,
                },
                "kpis": [
                    {
                        "metric_id": "SAC_KPI_OP_MARGIN",
                        "title": "Operating Profit Margin",
                        "value": "24.8%",
                        "target": "22.5%",
                        "variance": "+2.3%",
                        "status": "ON_TRACK",
                        "trend": "UPWARD",
                    },
                    {
                        "metric_id": "SAC_KPI_EBITDA",
                        "title": "EBITDA Performance",
                        "value": "AED 184.2M",
                        "target": "AED 175.0M",
                        "variance": "+5.25%",
                        "status": "ON_TRACK",
                        "trend": "UPWARD",
                    },
                    {
                        "metric_id": "SAC_KPI_CASH_CONV",
                        "title": "Cash Conversion Cycle",
                        "value": "42 Days",
                        "target": "45 Days",
                        "variance": "-3 Days",
                        "status": "ON_TRACK",
                        "trend": "FAVORABLE",
                    },
                    {
                        "metric_id": "SAC_KPI_CAPEX_UTIL",
                        "title": "Strategic Capex Utilization",
                        "value": "81.4%",
                        "target": "85.0%",
                        "variance": "-3.6%",
                        "status": "MONITOR",
                        "trend": "STABLE",
                    },
                ],
                "executive_summary": "Q3-2026 performance on SAP Analytics Cloud models exceeds financial operating targets by 2.3% margin with favorable cash conversion.",
            }
            cache.set(cache_key, data, ttl=120)
            return data

        # Live SAC query with Bearer token
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{settings.sac_tenant_url.rstrip('/')}/api/v1/dataexport/providers/sac/kpis",
                headers=headers,
                params={"domain": domain.upper()},
            )
            response.raise_for_status()
            data = response.json()
            data["isDemoData"] = False
            data["audit"] = {
                "executingIdentity": settings.executing_identity,
                "authorizationModel": settings.authorization_model,
            }
            cache.set(cache_key, data, ttl=120)
            return data

    async def get_story_analytics(self, story_id: str = "VELORA_CORP_PERF_2026") -> Dict[str, Any]:
        cache_key = f"sac_story_{story_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        token = await self.get_token()
        if not token:
            if not settings.demo_mode:
                raise RuntimeError("SAC live integration is not configured")
            data = {
                "source": "Synthetic demonstration data",
                "isDemoData": True,
                "story_id": story_id,
                "story_title": "Velora Corporate Strategy & Financial Outlook 2026",
                "audit": {
                    "executingIdentity": settings.executing_identity,
                    "authorizationModel": settings.authorization_model,
                },
                "pages": [
                    {
                        "page_name": "Executive Overview",
                        "key_dimensions": ["Fiscal Period", "Operating Entity", "Cost Center"],
                        "primary_insights": [
                            "Ground Handling Services revenue up 8.4% YoY in Abu Dhabi Hub.",
                            "Direct labor efficiencies optimized via SuccessFactors scheduling integration.",
                            "Total Capex commitments aligned with Phase 1 AgenticAD transformation.",
                        ],
                    },
                    {
                        "page_name": "Departmental Cost Variance",
                        "charts": [
                            {"name": "Budget vs Actual by Division", "top_favorable": "Tech & Innovation (+4.1%)", "top_unfavorable": "Fuel & Fleet (-1.8%)"},
                        ],
                    },
                ],
                "last_refreshed": "2026-08-15T06:00:00Z",
                "currency": "AED",
            }
            cache.set(cache_key, data, ttl=300)
            return data

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{settings.sac_tenant_url.rstrip('/')}/api/v1/stories/{story_id}",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            data["isDemoData"] = False
            data["audit"] = {
                "executingIdentity": settings.executing_identity,
                "authorizationModel": settings.authorization_model,
            }
            cache.set(cache_key, data, ttl=300)
            return data

    async def get_model_data(self, model_id: str, measures: Optional[List[str]] = None) -> Dict[str, Any]:
        cache_key = f"sac_model_{model_id}_{str(measures)}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        token = await self.get_token()
        if not token:
            if not settings.demo_mode:
                raise RuntimeError("SAC live integration is not configured")
            data = {
                "source": "Synthetic demonstration data",
                "isDemoData": True,
                "model_id": model_id,
                "measures_queried": measures or ["GrossRevenue", "OperatingExpense", "NetMargin"],
                "records_count": 12,
                "sample_aggregation": {
                    "GrossRevenue_AED": 412500000.0,
                    "OperatingExpense_AED": 310200000.0,
                    "NetMargin_AED": 102300000.0,
                },
                "status": "SUCCESS",
                "timestamp": "2026-08-15T07:00:00Z",
                "audit": {
                    "executingIdentity": settings.executing_identity,
                    "authorizationModel": settings.authorization_model,
                },
            }
            cache.set(cache_key, data, ttl=180)
            return data

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.sac_tenant_url.rstrip('/')}/api/v1/dataexport/providers/sac/models/{model_id}/query",
                headers=headers,
                json={"measures": measures or []},
            )
            response.raise_for_status()
            data = response.json()
            data["isDemoData"] = False
            data["audit"] = {
                "executingIdentity": settings.executing_identity,
                "authorizationModel": settings.authorization_model,
            }
            cache.set(cache_key, data, ttl=180)
            return data


sac_client = SACClient()
