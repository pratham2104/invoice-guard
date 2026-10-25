# Screenshot QA — PAYGUARD

Captured **2026-10-25** on dev host via Playwright (`scripts/capture_payguard_screenshots.mjs`) against `http://127.0.0.1:8767/payguard/`.

| Viewport | Status | File |
|----------|--------|------|
| 1440×900 | PASS | `artifacts/demo/payguard-1440x900-main.png` |
| 1280×720 | PASS | `artifacts/demo/payguard-1280x720-main.png` |
| 1024×768 | PASS | `artifacts/demo/payguard-1024x768-main.png` |
| 390×844 | PASS | `artifacts/demo/payguard-390x844-mobile.png` (2D trace) |

## Required UI states

| State | Status | File / note |
|-------|--------|-------------|
| SYNTHETIC DEMO header | PASS | visible in main shots (`data-testid=mode-badge`) |
| Blocked invoice + gate | PASS | invoice_redirect, isolate path, red banner text |
| Fork 3 policies populated | PASS | footer panel on load + 3D branch monoliths when fork enabled |
| Approval JSON (`ui_cannot_deploy_policy`) | PASS | `artifacts/demo/payguard-capture-meta.json` snippet |
| DISCONNECTED banner | PASS | `artifacts/demo/payguard-disconnected.png` |

## Re-run

```bash
python3 -m phantomshift --port 8767 &
cd phantomshift-starter && npm install -D playwright@1.50.1 && npx playwright install chromium
node scripts/capture_payguard_screenshots.mjs --base=http://127.0.0.1:8767
```

Classic console (non-PAYGUARD): `artifacts/demo/ui-desktop-dark.png`, `ui-desktop-light.png`.
