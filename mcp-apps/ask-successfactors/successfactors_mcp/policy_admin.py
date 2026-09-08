"""Velora Policy Administration & Preview Service.

Allows authorized administrators to manage Dataverse disclosure policies,
activate/deactivate versions, preview Restricted vs. Extended outputs, and purge caches.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from .dataverse_audit import get_dataverse_client
from .policy_engine import PROFILE_BASIC, PROFILE_WORKFORCE_DRILLDOWN, PERMANENTLY_PROHIBITED_FIELDS, get_policy_engine
from .cache import get_multi_layer_cache
from shared_mcp.logger import get_logger
log = get_logger('policy_admin')

class PolicyAdminService:
    """Enterprise policy lifecycle management and preview generation."""

    def __init__(self, dataverse_client=None, cache=None, policy_engine=None):
        self.client = dataverse_client or get_dataverse_client()
        self.cache = cache or get_multi_layer_cache()
        self.policy_engine = policy_engine or get_policy_engine()

    async def list_policies(self) -> List[Dict[str, Any]]:
        """List all policy versions in the Dataverse table."""
        return await self.client.list_policies()

    async def create_or_update_policy(self, policy_name: str, policy_code: str, version: str, allowed_fields: List[str], allow_group_drilldown: bool=True, maximum_result_rows: int=100, minimum_group_size: int=1, allowed_user_groups: Optional[List[str]]=None, is_active: bool=False, approved_by: str='Velora Governance Committee', change_reason: str='Policy update') -> Dict[str, Any]:
        """Create or update a disclosure policy entry."""
        clean_allowed_fields = [f for f in allowed_fields if f.lower() not in PERMANENTLY_PROHIBITED_FIELDS]
        policy_payload = {'cre2f_policyname': policy_name, 'cre2f_policycode': policy_code, 'cre2f_version': version, 'cre2f_isactive': is_active, 'cre2f_datadomain': 'Employee', 'cre2f_allowemployeesearch': True, 'cre2f_allowgroupdrilldown': allow_group_drilldown, 'cre2f_allowedemployeefields': json.dumps(clean_allowed_fields), 'cre2f_restrictedemployeefields': json.dumps(list(PERMANENTLY_PROHIBITED_FIELDS)), 'cre2f_maximumresultrows': maximum_result_rows, 'cre2f_minimumgroupsize': minimum_group_size, 'cre2f_allowedusergroups': json.dumps(allowed_user_groups or ['All_Velora_Authenticated']), 'cre2f_approvedby': approved_by, 'cre2f_approvaldate': datetime.now(timezone.utc).isoformat() if is_active else None, 'cre2f_changereason': change_reason}
        res = await self.client.save_policy(policy_payload)
        if is_active:
            await self.purge_policy_and_drilldown_cache()
        return res

    async def activate_policy(self, policy_id: str, approver: str='Velora HR Governance') -> Dict[str, Any]:
        """Activate a policy version and purge policy and drill-down caches."""
        policies = await self.client.list_policies()
        target = None
        for p in policies:
            if p.get('cre2f_veloradatadisclosurepolicyid') == policy_id:
                target = p
                break
        if not target:
            return {'error': True, 'message': f'Policy {policy_id} not found.'}
        target['cre2f_isactive'] = True
        target['cre2f_approvedby'] = approver
        target['cre2f_approvaldate'] = datetime.now(timezone.utc).isoformat()
        await self.client.save_policy(target)
        await self.purge_policy_and_drilldown_cache()
        log.info('policy_activated', policy_id=policy_id, version=target.get('cre2f_version'))
        return {'status': 'SUCCESS', 'message': f'Policy {policy_id} activated successfully.'}

    async def purge_policy_and_drilldown_cache(self) -> None:
        """Purge Layer 1 (Policy) and Layer 4 (Drill-Down) cache tiers."""
        await self.cache.policy_cache.clear()
        await self.cache.drilldown_cache.clear()
        log.info('policy_and_drilldown_cache_purged')

    def preview_policy_output(self, sample_query: str='Who are the 15 employees in the Unassigned department?', profile: str='workforce_drilldown') -> Dict[str, Any]:
        return {'status': 'SOURCE_UNAVAILABLE', 'message': 'Policy preview requires explicitly supplied, authorized input. Embedded employee examples have been removed.'}
_global_policy_admin = PolicyAdminService()

def get_policy_admin() -> PolicyAdminService:
    return _global_policy_admin
