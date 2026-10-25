"""Central configuration. Everything is overridable by environment variable."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.environ.get("APG_DB", ROOT / "apguard.db"))
INBOX_DIR = Path(os.environ.get("APG_INBOX", ROOT / "fixtures" / "inbox"))

# Secret used to fingerprint bank accounts (HMAC). Set a real one on the box.
FINGERPRINT_KEY = os.environ.get("APG_FINGERPRINT_KEY", "dev-only-change-me").encode()

# Local OpenAI-compatible endpoint (vLLM). Leave unset to run regex-only.
LLM_BASE_URL = os.environ.get("APG_LLM_BASE_URL", "")  # e.g. http://localhost:8000/v1
LLM_MODEL = os.environ.get("APG_LLM_MODEL", "qwen3.6-35b-a3b")  # vLLM --served-model-name
LLM_TIMEOUT = float(os.environ.get("APG_LLM_TIMEOUT", "30"))
LLM_MAX_TOKENS = int(os.environ.get("APG_LLM_MAX_TOKENS", "512"))
# Qwen3.x thinks by default. Extraction is a lookup, not reasoning: turn it off for speed.
LLM_THINKING = os.environ.get("APG_LLM_THINKING", "0") not in ("", "0", "false")

# Verdict thresholds
HOLD_SCORE = 40          # total risk points at or above this => HOLD
PO_TOLERANCE = 0.02      # invoice may exceed PO by 2% before flagging
LOOKALIKE_MAX_DISTANCE = 2

# Users and roles for the approval step (Slack user IDs in production).
# Override with APG_USERS='{"U012ABC": "ap_clerk", "U045DEF": "ap_manager"}'
USERS = json.loads(os.environ["APG_USERS"]) if os.environ.get("APG_USERS") else {
    "alice": "ap_clerk",
    "bob": "ap_manager",
    "carol": "ap_manager",
}
APPROVER_ROLES = {"ap_manager"}

# Set when the CLI is driven by an LLM agent (OpenClaw). The agent may read, triage and
# draft, but human-only actions (verify/confirm/approve/reject) and DB resets are refused.
AGENT_MODE = os.environ.get("APG_AGENT_MODE", "") not in ("", "0", "false")
AGENT_ALLOWED = {"process", "cases", "show", "audit", "draft", "verify-audit"}
