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
        if self._token and time.time() < self._token_expires_at - settings.oauth_token_cache_skew_seconds:
            return self._token
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(settings.sac_token_url, data={'grant_type': 'client_credentials'}, auth=(settings.sac_client_id, settings.sac_client_secret))
                if res.status_code == 200:
                    data = res.json()
                    self._token = data.get('access_token')
                    expires_in = data.get('expires_in', 3600)
                    self._token_expires_at = time.time() + expires_in
                    return self._token
        except Exception:
            pass
        return None

    async def get_executive_kpis(self, domain: str='FINANCE') -> Dict[str, Any]:
        cache_key = f'sac_kpi_{domain.upper()}'
        cached = cache.get(cache_key)
        if cached:
            if cached.get('isDemoData') or cached.get('simulated'):
                raise RuntimeError('Cached non-live data rejected; restart on the cleaned image')
            return cached
        token = await self.get_token()
        if not token:
            raise RuntimeError('SOURCE_UNAVAILABLE: get_executive_kpis requires a configured live provider; no substitute data is returned.')
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{settings.sac_tenant_url.rstrip('/')}/api/v1/dataexport/providers/sac/kpis", headers=headers, params={'domain': domain.upper()})
            response.raise_for_status()
            data = response.json()
            data['isDemoData'] = False
            data['audit'] = {'executingIdentity': settings.executing_identity, 'authorizationModel': settings.authorization_model}
            cache.set(cache_key, data, ttl=120)
            return data

    async def get_story_analytics(self, story_id: str='VELORA_CORP_PERF_2026') -> Dict[str, Any]:
        cache_key = f'sac_story_{story_id}'
        cached = cache.get(cache_key)
        if cached:
            if cached.get('isDemoData') or cached.get('simulated'):
                raise RuntimeError('Cached non-live data rejected; restart on the cleaned image')
            return cached
        token = await self.get_token()
        if not token:
            raise RuntimeError('SOURCE_UNAVAILABLE: get_story_analytics requires a configured live provider; no substitute data is returned.')
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{settings.sac_tenant_url.rstrip('/')}/api/v1/stories/{story_id}", headers=headers)
            response.raise_for_status()
            data = response.json()
            data['isDemoData'] = False
            data['audit'] = {'executingIdentity': settings.executing_identity, 'authorizationModel': settings.authorization_model}
            cache.set(cache_key, data, ttl=300)
            return data

    async def get_model_data(self, model_id: str, measures: Optional[List[str]]=None) -> Dict[str, Any]:
        cache_key = f'sac_model_{model_id}_{str(measures)}'
        cached = cache.get(cache_key)
        if cached:
            if cached.get('isDemoData') or cached.get('simulated'):
                raise RuntimeError('Cached non-live data rejected; restart on the cleaned image')
            return cached
        token = await self.get_token()
        if not token:
            raise RuntimeError('SOURCE_UNAVAILABLE: get_model_data requires a configured live provider; no substitute data is returned.')
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{settings.sac_tenant_url.rstrip('/')}/api/v1/dataexport/providers/sac/models/{model_id}/query", headers=headers, json={'measures': measures or []})
            response.raise_for_status()
            data = response.json()
            data['isDemoData'] = False
            data['audit'] = {'executingIdentity': settings.executing_identity, 'authorizationModel': settings.authorization_model}
            cache.set(cache_key, data, ttl=180)
            return data
sac_client = SACClient()
