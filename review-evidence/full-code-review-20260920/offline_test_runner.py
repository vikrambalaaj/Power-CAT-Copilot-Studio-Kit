"""Run one suite with isolated state, no provider credentials, and blocked sockets."""
import os
import socket
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
service, report = sys.argv[1:3]
retained = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"}}
os.environ.clear()
os.environ.update(retained)
scratch = tempfile.mkdtemp(prefix="velora-offline-review-")
os.environ.update(
    PYTHON_DOTENV_DISABLED="1",
    VELORA_STATE_DIR=scratch,
    VELORA_OUTBOX_DIR=scratch,
    FACILITATOR_STORAGE_DIR=scratch,
    AZURE_STORAGE_MOUNT_PATH=scratch,
    PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
)

def blocked(*args, **kwargs):
    raise RuntimeError("OFFLINE_REVIEW_NETWORK_BLOCKED")

socket.create_connection = blocked
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
directory = root / service
os.chdir(directory)
sys.path.insert(0, str(directory))
if "--workspace-imports" in sys.argv:
    sys.path.insert(0, str(root / "mcp-apps/ask-productivity"))
    sys.path.append(str(root / "mcp-apps/ask-facilitator"))
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files = lambda self: {}
import pytest
target = sys.argv[3] if len(sys.argv) > 3 else "test"
raise SystemExit(pytest.main([target, "-q", "--tb=short", "-p", "pytest_asyncio.plugin", "-o", "asyncio_mode=auto", "-p", "no:cacheprovider", "--junitxml=" + report]))
