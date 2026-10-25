"""Drain AUTOPATCH outbox to Discord (idempotent dedupe keys; dev REST channel)."""

from __future__ import annotations

from typing import Any, Callable

from .. import discord_views
from .events import AutopatchStore


def drain_outbox(
    store: AutopatchStore,
    post: Callable[[str, dict], Any],
    *,
    limit: int = 10,
) -> dict[str, Any]:
    """Post pending outbox rows; marks sent only after post succeeds."""
    sent = 0
    failed = 0
    for row in store.claim_outbox(limit=limit):
        try:
            payload = row["payload"]
            channel = row["channel"]
            if channel == "approvals":
                embed = discord_views.autopatch_finding_embed(payload)
                post("approvals", embed=embed)
            else:
                post(channel, content=f"AUTOPATCH outbox `{row['dedupe_key']}`")
            store.complete_outbox(row["id"], ok=True)
            sent += 1
        except OSError:
            store.complete_outbox(row["id"], ok=False)
            failed += 1
    return {"sent": sent, "failed": failed}
