"""Trusted deploy with backup, verify, rollback (sandbox policy store only)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from ..enforcement_pipeline import run_firewall_acceptance_test
from ..approval import config_digest
from ..policies import validate_config


class PolicyDeployService:
    def __init__(self, store_dir: str = "artifacts/autopatch/policies") -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._active_path = self.store_dir / "active.json"
        self._backup_path = self.store_dir / "last_good.json"

    def read_active_digest(self) -> str | None:
        if not self._active_path.exists():
            return None
        data = json.loads(self._active_path.read_text())
        return data.get("digest")

    def deploy(
        self,
        cfg: dict,
        *,
        expected_version: str | None,
        candidate_hash: str,
        finding_id: str,
    ) -> dict[str, Any]:
        deploy_id = f"dep-{uuid.uuid4().hex[:10]}"
        digest = candidate_hash
        if config_digest(cfg) != digest:
            return {"ok": False, "state": "FAILED", "reason": "candidate hash mismatch"}

        errs = validate_config(cfg)
        if errs:
            return {"ok": False, "state": "FAILED", "reason": f"validate_config: {errs}"}

        if self._active_path.exists():
            self._backup_path.write_text(self._active_path.read_text())

        record = {"config": cfg, "digest": digest, "finding_id": finding_id, "expected_version": expected_version}
        self._active_path.write_text(json.dumps(record, indent=2))

        verify = run_firewall_acceptance_test()
        if not verify.get("passed"):
            self._rollback()
            return {
                "ok": False,
                "state": "ROLLED_BACK",
                "deploy_id": deploy_id,
                "reason": "post-deploy acceptance failed",
                "verify": verify,
            }

        return {"ok": True, "state": "VERIFIED", "deploy_id": deploy_id, "digest": digest, "verify": verify}

    def _rollback(self) -> None:
        if self._backup_path.exists():
            self._active_path.write_text(self._backup_path.read_text())
        elif self._active_path.exists():
            self._active_path.unlink()

    def force_rollback(self, reason: str) -> dict:
        self._rollback()
        return {"ok": True, "state": "ROLLED_BACK", "reason": reason}

