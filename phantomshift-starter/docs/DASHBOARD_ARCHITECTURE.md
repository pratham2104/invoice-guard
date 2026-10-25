# PAYGUARD dashboard architecture

## Routes

| Route | Purpose |
|-------|---------|
| `/payguard/` | Vite-built React SPA (3D control plane) |
| `/` | Classic incident console (stdlib static) |
| `GET /api/dashboard/status` | Mode, gate projection from `verify.json`, connection flags |
| `GET /api/incidents` | Fixture incident index (`synthetic_demo`) |
| `GET /api/incidents/{id}` | Full incident via `incident.run_incident` + trace graph |
| `GET /api/incidents/{id}/trace` | Nodes/edges only |
| `GET /api/incidents/{id}/replays` | Three-policy matrix via `engine.replay` |
| `POST /api/incidents/{id}/replays` | Idempotent replay (no mutation) |
| `POST /api/incidents/{id}/approval-request` | **Status only** — cannot deploy policy |
| `GET /api/metrics` | Labeled financial + eval metrics |

## Trust boundaries

- UI never calls external LLM APIs; inference stays on GB10 backend when wired.
- Frontend cannot set approval to success; displays backend/simulated channel state only.
- Denied attacks render `denied_at_gate` edges — no green path to `external_effect` when `live_action.held`.
- `SYNTHETIC DEMO` is default until live gates and event store prove otherwise.

## Component map

```
payguard-ui/src/App.tsx
├── Incident rail (list from /api/incidents)
├── SecurityTraceCanvas (R3F: EventNodeMesh, CausalEdgeMesh)
├── Evidence inspector (HTML, selectable)
└── Outcome strip (metrics + replays)

phantomshift/dashboard.py — trace layout, API DTOs
phantomshift/server.py — Host allow-list, static payguard/, JSON routes
```

## Build

```bash
cd payguard-ui && npm ci && npm run build
# output: phantomshift/static/payguard/
python3 -m phantomshift
# open http://127.0.0.1:8765/payguard/
```
