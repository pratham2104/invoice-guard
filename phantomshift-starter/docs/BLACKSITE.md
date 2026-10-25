# PHANTOMSHIFT BLACKSITE (2D command center)

**Route:** `/payguard/` (built from `payguard-ui/` → `phantomshift/static/payguard/`)

## Product spine

Untrusted input → agent / Nemotron → proposed tool → **trust boundary** → block or allow → policy lab replay → Discord review (server-side) → verification receipt.

## Workspaces

| Tab | Purpose |
|-----|---------|
| **Control** | Incident rail, React Flow causality graph, evidence inspector, AUTOPATCH lane, reality strip |
| **Policy lab** | Baseline / lockdown / context-bound lanes with attack & legit denominators |
| **Evidence** | Incident table, held-out baselines from `artifacts/benchmarks/baselines.json`, historical Nano 4B row (labeled) |

## Data modes (always visible)

- **SYNTHETIC DEMO** — default fixture incidents from `dashboard.py`
- **HISTORICAL BENCHMARK** — Evidence tab + hero KPIs sourced from `/api/evidence/benchmarks` (see `CLAIMS_AUDIT.md`)
- **LIVE VERIFIED** — only when readiness gates and backend say so (not expected on dev host)
- **DISCONNECTED** — QA toggle or fetch failure; no silent live claims

## API (read-only UI)

- Existing: `/api/dashboard/status`, `/api/incidents*`, `/api/metrics`
- Added: `/api/autopatch/events`, `/api/autopatch/findings`, `/api/evidence/benchmarks`

## Tech

- React 19, Vite, Tailwind, TanStack Query, **@xyflow/react** (2D graph), Motion not required for core path
- **No Three.js / R3F** in production bundle (removed 2026-10-25)

## Run locally

```bash
cd payguard-ui && npm run build
python3 -m phantomshift   # default :8765
open http://127.0.0.1:8765/payguard/
```

Screenshots: `node scripts/capture_payguard_screenshots.mjs --base=http://127.0.0.1:8765`

## Demo guide

In-app **Demo** button — manual steps, SYNTHETIC DEMO banner, no autoplay backend fiction.
