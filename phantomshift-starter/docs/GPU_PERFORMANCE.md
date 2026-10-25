# GPU / scene performance

## Scene budget (PAYGUARD)

- Single `@react-three/fiber` Canvas, `dpr={[1, 1.5]}`, `frameloop="demand"`.
- Node count capped by incident trace (typically &lt;12 nodes per fixture).
- No postprocessing, shadows, or HDRI in P0.
- Idle motion: subtle Y oscillation; disabled via **Motion** toggle or `prefers-reduced-motion`.

## Measurements

| Environment | FPS | Notes |
|-------------|-----|-------|
| Dev server (x86, RTX 3090) | NOT_TESTED | UI build succeeded; no frame time capture this pass |
| GB10 event hardware | NOT_TESTED | Required before claiming demo readiness |

## Inference contention

When Nemotron serves on GB10, prefer **Static** motion off during live inference demos. No automatic degradation hook yet — manual toggle only.

## Bundle

Production JS ~1.2 MB minified (Three + R3F). Acceptable for LAN localhost demo; code-splitting marked P2.
