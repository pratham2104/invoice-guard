# Offline kit (scaffold)

Nothing here is staged yet: no weights, no images.

Target is arm64 Linux (GB10); this dev host is x86_64. Do not assume wheels, CUDA builds or images transfer.

1. Source: `git bundle` or tar of this repo (stdlib only, portable).
2. Models: take the profile from `nemoclaw profiles list` on the GB10 and the NVIDIA playbook, check licence, then download to `models/`. Record the exact model id and revision.
3. Images: pull with `--platform linux/arm64` and save digests; verify they load on the GB10.
4. Run `scripts/make_manifest.sh <dir>` to write `manifest.sha256`; re-check on the target with `sha256sum -c`.
5. No secrets on the drive. Bot tokens stay in each member's own environment.

## Staged on the dev box (not in git): `/home/923873155/Dell X NVIDIA Hack/offline-stage/`
- `NemoClaw-f00fb1d-src.tar.gz`: NVIDIA/NemoClaw `lkg` at f00fb1d, .git stripped (docs + installer + blueprint).
- `nemoclaw-bootstrap.sh`: the official https://www.nvidia.com/nemoclaw.sh as downloaded (sha256 539c25cf...). Read; it only clones and runs scripts/install.sh.
- `images/openclaw-sandbox-arm64.tar`: pinned sandbox image, linux/arm64 (see docs/GB10_RUNBOOK.md for digests), if the pull finished.
- NOT staged: OpenShell 0.0.116 binary, `@nvidia/openshell-sdk` npm packages (GitHub npm registry), OpenClaw npm tarball, model weights. The installer fetches these at install time, so the GB10 needs network or these must be pre-staged on site.
Re-verify with `sha256sum -c` on the GB10.

## Status update (2026-10-24 ~10:35Z)
- Verified: `images/openclaw-sandbox-arm64.tar` passes `sha256sum -c` (run from the stage root, the checksum file uses stage-relative paths) and `docker load` reports image ID `sha256:f0975cb4...` = the pinned arm64 manifest digest. Loaded on an x86_64 host only; never run.
- Staged and checksummed: `models/nemotron-3.5-lightning-30b-a3b-nvfp4` (21.6 GB, rev 0dcd680e...), `images/vllm-openai-arm64.tar` (12 GB, `vllm/vllm-openai@sha256:3af90144...`). Not run anywhere (needs a GB10, compute capability 12.1).
- Fallback (Nemotron-3 Nano 4B FP8 + `nvcr.io/nvidia/vllm@sha256:9204569b...`) and the full `manifest.sha256` are being produced by background scripts; check `offline-stage/fetch_fallback.log` and `offline-stage/package.log`.
- NemoClaw docs list offline installs as unsupported: the GB10 still needs network for the installer, OpenShell and OpenClaw packages.
