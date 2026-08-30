"""Pinned Standard and profile validation runner."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
from datetime import datetime, timezone
from typing import Any

from . import __version__


PROFILE_SCRIPTS = {
    "organization": "validate_organization_twin.py",
    "project": "validate_project_twin.py",
    "donor-funder": "validate_donor_funder_twin.py",
    "product": "validate_product_twin.py",
    "verified-impact": "validate_verified_impact_twin.py",
}


class ConformanceError(RuntimeError):
    """A fail-closed precondition or validation failure."""


def load_lock(path: Path) -> dict[str, str]:
    lock = json.loads(path.read_text(encoding="utf-8"))
    required = {"repository", "tag", "commit"}
    if set(lock) != required or len(lock["commit"]) != 40:
        raise ConformanceError("standard-lock-invalid")
    return lock


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def normalize_repository(value: str) -> str:
    return value.removesuffix(".git").removesuffix("/").lower()


def verify_standard_checkout(
    standard_root: Path, expected_commit: str, expected_repository: str
) -> str:
    if not (standard_root / ".git").exists():
        raise ConformanceError("standard-checkout-not-git")
    head = run(["git", "rev-parse", "HEAD"], standard_root)
    if head.returncode:
        raise ConformanceError("standard-head-unreadable")
    actual = head.stdout.strip()
    if actual != expected_commit:
        raise ConformanceError(f"standard-commit-mismatch:{actual}")
    origin = run(["git", "remote", "get-url", "origin"], standard_root)
    if origin.returncode or normalize_repository(origin.stdout.strip()) != normalize_repository(expected_repository):
        raise ConformanceError("standard-origin-mismatch")
    state = run(["git", "status", "--porcelain"], standard_root)
    if state.returncode or state.stdout.strip():
        raise ConformanceError("standard-worktree-not-clean")
    return actual


def execute_standard_gate(standard_root: Path) -> subprocess.CompletedProcess[str]:
    return run(["make", "check"], standard_root)


def execute_profile_validation(
    standard_root: Path, profile: str, instance_path: Path
) -> subprocess.CompletedProcess[str]:
    try:
        script = PROFILE_SCRIPTS[profile]
    except KeyError as exc:
        raise ConformanceError(f"unsupported-profile:{profile}") from exc
    if not instance_path.is_file():
        raise ConformanceError("instance-not-found")
    return run(["python3", str(standard_root / "scripts" / script), str(instance_path)], standard_root)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def report(
    *,
    mode: str,
    standard_commit: str,
    standard_tag: str,
    outcome: str,
    command: list[str],
    target: Path | None,
    process: subprocess.CompletedProcess[str] | None,
    failure: str | None = None,
    harness_commit: str | None = None,
) -> dict[str, Any]:
    return {
        "report_version": "0.1.0",
        "claim_type": "self_assessment_test_evidence",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "harness": {"version": __version__, "commit": harness_commit},
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "mode": mode,
        "standard": {"tag": standard_tag, "commit": standard_commit},
        "target": None if target is None else {"path": str(target), "sha256": file_sha256(target)},
        "outcome": outcome,
        "command": command,
        "exit_code": None if process is None else process.returncode,
        "stdout": "" if process is None else process.stdout[-12000:],
        "stderr": "" if process is None else process.stderr[-12000:],
        "failure": failure,
        "limitations": [
            "This report is not a certification.",
            "It does not prove factual claims, authorization, security, privacy, legal or donor compliance.",
            "It covers only the pinned Standard release, target bytes and commands identified here.",
        ],
    }


def current_harness_commit(root: Path) -> str | None:
    result = run(["git", "rev-parse", "HEAD"], root)
    return result.stdout.strip() if result.returncode == 0 else None
