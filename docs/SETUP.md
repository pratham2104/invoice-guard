# GB10 setup (what we did, in order)

Credentials are NOT in this repo. Ask a teammate.

## 0. Network
- Put the GB10 and your laptop on the **same phone hotspot**. Venue Wi-Fi keeps devices apart.
- On the GB10: `hostname -I` → first address is the box's IP.
- SSH: `ssh-copy-id dell@<ip>` once from your Mac's Terminal app, then `ssh dell@<ip>`.
- If SSH is closed: on the GB10, `sudo systemctl enable --now ssh`.

## 1. Model from the USB drive (no download)
```
mkdir -p ~/.cache/huggingface && cp -r /media/$USER/HACKATHON/hf/hub ~/.cache/huggingface/ \
  && find ~/.cache/huggingface/hub -name '._*' -delete
du -sh ~/.cache/huggingface/hub/models--nvidia--Qwen3.6-35B-A3B-NVFP4   # ~22G
```
Shard sizes (bytes): 10006877608 / 10003595752 / 3413864960.

The installer asks for revision `491c2f1e…`; the drive had `1355db6a…`. Weights are
identical (only README differs), so a `snapshots/491c2f1e…` folder was added that reuses the
same files. This should stop the installer re-downloading 23.5 GB. Status: unconfirmed until
the installer runs.

## 2. NemoClaw installer (~11–12 GB download: vLLM image 9.6 GB + sandbox images)
Needs internet and the sudo password. Prefer venue Wi-Fi for this step.
```
NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1 bash /media/$USER/HACKATHON/nemoclaw.sh 2>&1 | tee ~/nemoclaw-install.log
```
- "Choose 1 or 2" → `2` (recipe `vllm.qwen3-6-35b-a3b-nvfp4.spark-single.v1`)
- "Express install" → Enter
- If it starts downloading a ~23 GB model, stop it: the revision fix didn't work.

## 3. Open the agent
```
source ~/.bashrc
nemoclaw my-assistant dashboard-url --quiet
```
Open the printed `http://127.0.0.1:18790/#token=...` in the GB10's browser.

## Troubleshooting
- `nemoclaw my-assistant status` · `nemoclaw my-assistant logs --follow` · `nemoclaw my-assistant recover`

## Status log
- 12:00 — model copied and verified; installer not yet run.
