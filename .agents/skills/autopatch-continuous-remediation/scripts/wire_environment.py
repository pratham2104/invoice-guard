#!/usr/bin/env python3
"""Environment discovery and wiring for PHANTOMSHIFT AUTOPATCH.

Probes the local machine to determine whether it is running on the competition
Dell Pro Max GB10 (ARM64), a development workstation (x86_64), or a container sandbox.
Detects local Nemotron endpoints, staged model weights, OpenClaw/OpenShell binaries,
Docker bridge availability, and Discord configuration. Never prints credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent


def detect_gpus() -> list[str]:
    """Detect available NVIDIA GPUs via nvidia-smi without failing."""
    if not shutil.which("nvidia-smi"):
        return []
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if res.returncode == 0:
            return [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
    except Exception:
        pass
    return []


def probe_local_endpoint(url: str, timeout_s: float = 1.0) -> bool:
    """Probe whether a local loopback model endpoint is listening."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "autopatch-wire/1.0"})
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status in (200, 404, 405)
    except Exception:
        return False


def detect_docker_mode() -> dict[str, Any]:
    """Detect docker availability and whether rootless daemon is used."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return {"installed": False, "rootless": None}
    try:
        res = subprocess.run(
            ["docker", "info", "--format", "{{.SecurityOptions}}"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        out = res.stdout.lower()
        rootless = "rootless" in out
        return {"installed": True, "rootless": rootless}
    except Exception:
        return {"installed": True, "rootless": None}


def detect_staged_weights(root: Path) -> dict[str, bool]:
    """Check staged model directories for required weight files."""
    stage = root / "offline-stage"
    if not stage.is_dir() and (root.parent / "offline-stage").is_dir():
        stage = root.parent / "offline-stage"
    models_dir = stage / "models" if (stage / "models").is_dir() else stage / "nvidia"
    has_30b = (
        (models_dir / "nemotron-3.5-lightning-30b-a3b-nvfp4").is_dir()
        or (models_dir / "nemotron-3.5-lightning-30b-nvfp4").is_dir()
    )
    has_4b = (models_dir / "nemotron-3-nano-4b-fp8").is_dir()
    manifest = (stage / "manifest.sha256").is_file()
    return {
        "nemotron_30b_nvfp4": has_30b,
        "nemotron_4b_fp8": has_4b,
        "manifest_present": manifest,
        "stage_path": str(stage) if stage.is_dir() else None,
    }


def detect_discord_config(root: Path) -> dict[str, Any]:
    """Inspect Discord configuration presence without printing token values."""
    env_file = root / ".env"
    token_present = bool(os.environ.get("DISCORD_BOT_TOKEN"))
    guild_id = os.environ.get("DISCORD_GUILD_ID")
    operator_id = os.environ.get("DISCORD_OPERATOR_ID")

    if env_file.is_file():
        try:
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("DISCORD_BOT_TOKEN="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    token_present = token_present or bool(val)
                elif line.startswith("DISCORD_GUILD_ID="):
                    guild_id = guild_id or line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("DISCORD_OPERATOR_ID="):
                    operator_id = operator_id or line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass

    return {
        "token_configured": token_present,
        "guild_id_configured": bool(guild_id),
        "operator_id_configured": bool(operator_id),
    }


def wire_environment(root: Path | None = None) -> dict[str, Any]:
    """Build full environment wiring profile."""
    r = root or ROOT
    arch = platform.machine()
    is_gb10 = (arch == "aarch64")
    gpus = detect_gpus()

    # Local model server checks
    vllm_listening = probe_local_endpoint("http://127.0.0.1:8000/v1/models")
    ollama_listening = probe_local_endpoint("http://127.0.0.1:11434/api/tags")

    # Stack tools
    tools = {
        "nemoclaw": bool(shutil.which("nemoclaw")),
        "openclaw": bool(shutil.which("openclaw")),
        "openshell": bool(shutil.which("openshell")),
        "python3": bool(shutil.which("python3")),
    }

    # Staged assets
    weights = detect_staged_weights(r)
    docker = detect_docker_mode()
    discord = detect_discord_config(r)

    # Classify runtime tier
    if is_gb10 and vllm_listening and tools["openclaw"]:
        tier = "GB10_PRODUCTION_AIRGAP"
    elif not is_gb10 and tools["python3"]:
        tier = "DEV_HOST_SIMULATION"
    else:
        tier = "CONTAINER_MICRO_SANDBOX"

    profile = {
        "host": {
            "hostname": socket.gethostname(),
            "machine": arch,
            "system": platform.system(),
            "release": platform.release(),
            "is_gb10_arm64": is_gb10,
            "gpus": gpus,
            "tier": tier,
        },
        "inference": {
            "vllm_loopback_active": vllm_listening,
            "ollama_loopback_active": ollama_listening,
            "staged_weights": weights,
            "preferred_model": "Nemotron-3.5-Lightning-30B" if is_gb10 else "Nemotron-3-Nano-4B-CPU",
        },
        "stack": {
            "binaries": tools,
            "docker": docker,
        },
        "channels": {
            "discord": discord,
            "simulated_channel_available": True,
        },
        "recommended_ports": {
            "ui_server": 8765,
            "adapter_firewall": 7890,
            "local_vllm": 8000,
        },
    }
    return profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover and wire AUTOPATCH environment")
    parser.add_argument("--out", type=str, default="", help="Optional path to write profile JSON")
    parser.add_argument("--quiet", action="store_true", help="Do not print profile to stdout")
    args = parser.parse_args()

    profile = wire_environment()
    out_json = json.dumps(profile, indent=2)

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out_json + "\n")
        if not args.quiet:
            print(f"Environment profile written to {p}")
    elif not args.quiet:
        print(out_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
