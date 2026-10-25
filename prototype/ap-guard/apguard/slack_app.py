"""Slack layer (Socket Mode, no public URL needed).

NOT exercised in the cloud build environment - test it on the box.

Env:  SLACK_BOT_TOKEN (xoxb-...), SLACK_APP_TOKEN (xapp-..., Socket Mode),
      APG_SLACK_CHANNEL (channel ID for case cards)
Setup: create a Slack app, enable Socket Mode + Interactivity, add scopes chat:write, users:read.
Slack user IDs must be mapped to roles in config.USERS (e.g. {"U012ABC": "ap_manager"}).

What it does:
  * a background thread watches the inbox and posts a card for every new HOLD case
  * buttons: Start verification / Vendor confirmed / Vendor denied / Approve / Reject
  * all control rules live in cases.py, so Slack can't bypass them (errors shown ephemerally)
  * cards carry a summary only (vendor, severity, rule names); invoice data stays on the box
"""
import os
import threading
import time

from . import cases, config, db, pipeline

SEV_EMOJI = {"critical": ":rotating_light:", "high": ":warning:", "medium": ":large_yellow_circle:", "info": ":white_circle:"}


def case_blocks(conn, case_id: str) -> list:
    import json
    c = cases.get_case(conn, case_id)
    m = conn.execute("SELECT * FROM messages WHERE id=?", (c["message_pk"],)).fetchone()
    v = conn.execute("SELECT name FROM vendors WHERE id=?", (c["vendor_id"],)).fetchone()
    # Summary only: rule names, never sender, subject, amounts, invoice or bank numbers.
    findings = sorted(json.loads(m["findings_json"]), key=lambda f: -f["points"])
    rules_line = ", ".join(f"`{f['rule']}`" for f in findings[:3])
    state = c["state"]
    buttons = []
    if state == "OPEN":
        buttons.append(("Start verification", "start_verification", "primary"))
    if state == "AWAITING_VENDOR":
        buttons += [("Vendor confirmed", "vendor_confirmed", "primary"), ("Vendor denied", "vendor_denied", "danger")]
    if state == "READY_FOR_APPROVAL":
        buttons.append(("Approve", "approve", "primary"))
    if state not in cases.TERMINAL:
        buttons.append(("Reject", "reject", "danger"))
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{c['id']} - payment HELD ({c['severity'].upper()}, {c['risk_score']}/100)"}},
        {"type": "section", "text": {"type": "mrkdwn", "text":
            f"{SEV_EMOJI[c['severity']]} *Vendor:* {v['name'] if v else 'unknown'}\n*State:* `{state}`\n"
            f"*Why:* {rules_line}\n_Alerts are a heads-up; the data stays on the box "
            f"(`python -m apguard show {c['id']}`)._"}},
    ]
    if buttons:
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": t}, "action_id": a, "value": c["id"],
             **({"style": s} if s else {})} for t, a, s in buttons]})
    return blocks


def run(conn=None):
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app = App(token=os.environ["SLACK_BOT_TOKEN"])
    channel = os.environ["APG_SLACK_CHANNEL"]
    lock = threading.Lock()  # sqlite connection is shared across threads below

    def own_conn():
        return db.connect()

    def refresh(body, client, case_id):
        c = own_conn()
        try:
            client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"],
                               blocks=case_blocks(c, case_id), text=f"{case_id} update")
        finally:
            c.close()

    def handler(action_id, fn):
        @app.action(action_id)
        def _h(ack, body, client, respond):
            ack()
            case_id = body["actions"][0]["value"]
            user = body["user"]["id"]
            c = own_conn()
            try:
                fn(c, case_id, user)
                c.commit()
            except cases.ControlError as e:
                respond(text=f":no_entry: Blocked: {e}", response_type="ephemeral", replace_original=False)
                return
            finally:
                c.close()
            refresh(body, client, case_id)

    handler("start_verification", lambda c, i, u: cases.start_verification(c, i, u))
    handler("vendor_confirmed", lambda c, i, u: cases.record_confirmation(c, i, u, True, "via Slack"))
    handler("vendor_denied", lambda c, i, u: cases.record_confirmation(c, i, u, False, "via Slack"))
    handler("approve", lambda c, i, u: cases.approve(c, i, u))
    handler("reject", lambda c, i, u: cases.reject(c, i, u, "via Slack"))

    def watcher():
        c = own_conn()
        posted = set()
        while True:
            try:
                for r in pipeline.process_dir(c, config.INBOX_DIR):
                    if r.case_id and not r.skipped and r.case_id not in posted:
                        app.client.chat_postMessage(channel=channel, blocks=case_blocks(c, r.case_id),
                                                    text=f"{r.case_id} payment held")
                        posted.add(r.case_id)
            except Exception as e:  # keep the agent alive
                print("watcher error:", e)
            time.sleep(5)

    threading.Thread(target=watcher, daemon=True).start()
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
