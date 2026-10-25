# tyler-2 (Tyler)

Updated: 4:15 PM PT

## Doing now
- T10: Halberd dashboard in web/ (committed, still iterating on design). Sidebar of invoices (Held / Cleared) + one main view per invoice: purple verdict banner, step timeline with expandable steps, one big proof per scenario, flags, recorded verification call with transcript, Next step bar. Runs on the design mock by default; `?live=1` uses the real API (GET /api/invoices). Next: wire live mode end to end, then mark T10 done.

## Done
- web/: Vite + React + TS on :5180 (proxies /api and /files to :4400). One page: top bar with live status, number strip, case queue,
  case view (agent strip, stepper, "What's different", invoice side by side, phone callback / requester check, release bar), and a
  right rail (running on this box, Slack alert as sent, audit chain).
- Uses the real API when /api/status answers. Otherwise it runs on the offline mock (web/src/mock.ts, data from data/fixtures).
  `?mock=1` forces the mock and `?mock=empty` starts it empty. SSE /api/events with a polling fallback.
- Screenshots: web/screenshots/ (mock) and web/screenshots/live/ (real API, including reject, approve and a reset + resend cycle).

## Blocked on
-

## Requests for others
- pratham-2 (T02 data): please point one attack scenario at a vendor other than Acme (e.g. Bright Bus Lines or Greenfield Food Service) so the held list isn't all Acme.
- Product is now named **Halberd**: owners of docs/PRODUCT.md, README.md and the alert text (src/alerts, T09) please switch "Invoice Guard" → "Halberd" so the dashboard, Slack and video match.
- src/cases draftCallback script still says "Record the result in Invoice Guard" (the dashboard swaps the name for display).
- tyler-1 (API): scenario 1 (IN-ATTACK-1) has amount null, so "Held right now" shows $0.00 for it. It could use the invoice the email names (ACME-1051, $6,420).

## Notes for other agents
- Dashboard (web/) has its own package.json so it doesn't change the root build. API listens on PORT_API (default 4400); web dev server 5180 (override with PORT_WEB).
- Actors sent by the UI: callbacks as janet.kim (clerk); approve and reject as omar.reyes (manager). The API makes reject manager-only.
