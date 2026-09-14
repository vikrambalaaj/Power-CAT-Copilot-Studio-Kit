"""Offline tests of health-check evidence labeling, never business acceptance."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import urllib.error

path = Path(__file__).resolve().parents[2] / 'deploy/test_all_live_systems_and_audit.py'
spec = importlib.util.spec_from_file_location('health_review', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_provider_failure_never_reports_healthy_or_audit_success():
    with patch.object(module.urllib.request, 'urlopen', side_effect=urllib.error.URLError('test outage')):
        result = module.test_service_record(module.SERVICES[0])
    assert result['health_status'] == 'FAILED'
    assert result['audit_write_status'] == result['audit_readback_status'] == 'NOT_RUN'
    assert result['aatc_status'] == 'INCOMPLETE'
    assert 'audit_record' not in result

def test_health_success_cannot_complete_aatc(capsys):
    with patch.object(module, 'test_service_record', return_value={'health_status':'HEALTHY'}):
        assert module.main() == 2
    assert 'INCOMPLETE' in capsys.readouterr().out
