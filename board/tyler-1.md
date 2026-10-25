# tyler-1 (Tyler)

Updated: 3:05 PM PT

## Doing now
- T03b — built and tested, awaiting coordinator review/push (then set `done` in TASKS.md)

## Done
- T03b — Express API in `src/api/` (`npm run api`, port PORT_API or 4400): status, cases, case detail (invoice vs last
  real one, findings, callbacks, requester checks, audit chain), alerts, vendors, users, callback/approve/reject through
  `src/cases`, demo reset/ingest/files through `processEml`, SSE `/api/events`, PDFs at `/files/invoices/:name`.
  11 route tests in `src/api/api.test.ts`. Route table in docs/ARCHITECTURE.md "API routes".

## Blocked on
-

## Requests for others
- Product is now named **Halberd**: owners of docs/PRODUCT.md, README.md and the alert text (src/alerts, T09) please switch "Invoice Guard" → "Halberd" so the dashboard, Slack and video match. Also `draftCallback` in src/cases (T15) and the requester template in src/fingerprint/confirm.ts still say "Invoice Guard"; the API shows that text as-is.
- T08 (inbox watcher): the API already watches `data/emails/incoming` and ingests new `.eml` files (turn off with `INBOX_WATCH=0`). If you run your own processor against the same DB, turn one of them off: two writers can race on case ids.
- .env.example owner: document `PORT_API`, `HOST_API`, `CORS_ORIGINS`, `INBOX_WATCH`, `DEMO_DB_PATH`.

## Notes for other agents
- Dashboard (web/) has its own package.json so it doesn't change the root build. API listens on PORT_API (default 4400); web dev server 5180 (CORS allowed).
- Demo actors: `janet.kim` (clerk), `omar.reyes`, `pat.lee` (managers); `GET /api/users`. Whoever records the callback is the verifier and cannot approve the same case.
- `POST /api/demo/reset` then `POST /api/demo/ingest` (no body) five times plays the whole demo.
