import os, sys, socket, tempfile
from pathlib import Path
service, out = sys.argv[1:3]
root = Path('/Users/vikrambala/copilotstudio')
# Tests never inherit production credentials or load local dotenv files.
keep = {k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','TMPDIR','SYSTEMROOT')}
os.environ.clear(); os.environ.update(keep)
scratch = tempfile.mkdtemp(prefix='velora-aatc-tests-')
os.environ.update(HOME=scratch, PYTHON_DOTENV_DISABLED='1', VELORA_STATE_DIR=scratch, VELORA_OUTBOX_DIR=scratch, FACILITATOR_STORAGE_DIR=scratch, AZURE_STORAGE_MOUNT_PATH=scratch)
def blocked(*a, **kw): raise RuntimeError('OFFLINE_REVIEW_NETWORK_BLOCKED')
socket.create_connection=blocked
socket.socket.connect=blocked
socket.socket.connect_ex=blocked
os.chdir(root/'mcp-apps'/service)
sys.path.insert(0,str(Path.cwd()))
from pydantic_settings import BaseSettings
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files = lambda self: {}
import pytest
raise SystemExit(pytest.main(['test','-q','--tb=short','--junitxml='+out]))
