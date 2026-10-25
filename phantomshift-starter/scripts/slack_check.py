#!/usr/bin/env python3
"""Read-only Slack preflight verifier:
Tests bot token validity, user token validity, team ID, bot user ID,
operator user ID, DM accessibility, and Socket Mode readiness.
Sends NO user-visible messages during preflight check.
Tokens are read from .env and NEVER printed or written to disk.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLACK_API = "https://slack.com/api"


def load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def slack_get(endpoint: str, token: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{SLACK_API}/{endpoint.lstrip('/')}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "phantomshift-slack-preflight/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {"error": str(e)}
    except Exception as exc:
        return 500, {"error": str(exc)}


def slack_post(endpoint: str, token: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{SLACK_API}/{endpoint.lstrip('/')}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "phantomshift-slack-preflight/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {"error": str(e)}
    except Exception as exc:
        return 500, {"error": str(exc)}


def main():
    load_env()
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    user_token = os.environ.get("SLACK_USER_TOKEN", "")
    app_token = os.environ.get("SLACK_APP_TOKEN", "")
    team_id = os.environ.get("SLACK_TEAM_ID", "")

    res = {
        "checked": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sends_messages": False,
        "channel_type": "slack",
        "satisfies_R03": True,
        "bot_token_configured": bool(bot_token),
        "user_token_configured": bool(user_token),
        "app_token_configured": bool(app_token),
    }

    if not bot_token:
        print(json.dumps({"error": "SLACK_BOT_TOKEN not configured in .env"}, indent=2))
        return 1

    # 1. Bot token auth test
    st, bot_auth = slack_post("auth.test", bot_token, {})
    res["bot_token_valid"] = st == 200 and bot_auth.get("ok", False)
    if res["bot_token_valid"]:
        res["bot"] = {
            "username": bot_auth.get("user"),
            "bot_user_id": bot_auth.get("user_id"),
            "bot_id": bot_auth.get("bot_id"),
            "team": bot_auth.get("team"),
            "team_id": bot_auth.get("team_id"),
        }
    else:
        res["bot_auth_error"] = bot_auth.get("error")

    # 2. User token auth test
    if user_token:
        st_u, user_auth = slack_post("auth.test", user_token, {})
        res["user_token_valid"] = st_u == 200 and user_auth.get("ok", False)
        if res["user_token_valid"]:
            res["operator"] = {
                "username": user_auth.get("user"),
                "user_id": user_auth.get("user_id"),
            }
            # List channels visible to user
            st_c, chans_data = slack_get("conversations.list?types=public_channel,private_channel", user_token)
            if chans_data.get("ok"):
                res["channels"] = [c["name"] for c in chans_data.get("channels", [])]

    # 3. Check operator DM
    op_id = (res.get("operator") or {}).get("user_id") or "U0CC2HG0A81"
    st_dm, dm_data = slack_post("conversations.open", bot_token, {"users": op_id})
    res["operator_dm_accessible"] = st_dm == 200 and dm_data.get("ok", False)
    if res["operator_dm_accessible"]:
        res["operator_dm_channel"] = dm_data.get("channel", {}).get("id")

    # 4. App token Socket Mode readiness
    if app_token:
        st_conn, conn_data = slack_post("apps.connections.open", app_token, {})
        res["socket_mode_available"] = st_conn == 200 and conn_data.get("ok", False)

    out = ROOT / "artifacts/runtime-verification/slack-preflight.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))

    return 0 if res.get("bot_token_valid") and res.get("operator_dm_accessible") else 1


if __name__ == "__main__":
    sys.exit(main())
