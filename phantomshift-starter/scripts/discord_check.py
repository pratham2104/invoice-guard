#!/usr/bin/env python3
"""Read-only Discord preflight: is the token valid, is the bot in the server, which
channels can it see, and is the operator ID well-formed. Sends NO messages.

This does NOT satisfy hackathon R03. R03 needs the OpenClaw-managed channel on the GB10.
The token is read from .env or the environment and never printed or written to disk.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://discord.com/api/v10"


def load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get(path, token):
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bot {token}", "User-Agent": "phantomshift-preflight (local, 0.2)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:200]}


def main():
    load_env()
    token, guild, user = (os.environ.get(k, "") for k in ("DISCORD_BOT_TOKEN", "DISCORD_SERVER_ID", "DISCORD_USER_ID"))
    res = {"checked": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "sends_messages": False,
           "satisfies_R03": False, "note": "OpenClaw-managed channel on the GB10 is still required"}
    if not token:
        print("no DISCORD_BOT_TOKEN"); return 1
    res["ids_wellformed"] = {"server": guild.isdigit(), "user": user.isdigit()}
    st, me = get("/users/@me", token)
    res["token_valid"] = st == 200
    if st == 200:
        res["bot"] = {"username": me.get("username"), "id_suffix": str(me.get("id"))[-4:]}
        st2, guilds = get("/users/@me/guilds", token)
        res["in_target_server"] = st2 == 200 and any(g["id"] == guild for g in guilds)
        if res["in_target_server"]:
            st3, chans = get(f"/guilds/{guild}/channels", token)
            if st3 == 200:
                res["text_channels"] = sorted(c["name"] for c in chans if c["type"] == 0)
            st4, appinfo = get("/oauth2/applications/@me", token)
            if st4 == 200:
                flags = appinfo.get("flags", 0)
                res["intents"] = {"message_content": bool(flags & ((1 << 18) | (1 << 19))),
                                  "guild_members": bool(flags & ((1 << 14) | (1 << 15)))}
            st5, m = get(f"/guilds/{guild}/members/{user}", token)
            res["operator_is_member"] = st5 == 200
    else:
        res["error_status"] = st
    out = ROOT / "artifacts/runtime-verification/discord-preflight.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
    return 0 if res.get("token_valid") and res.get("in_target_server") else 1


if __name__ == "__main__":
    sys.exit(main())
