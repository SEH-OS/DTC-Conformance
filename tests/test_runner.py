from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from dtc_conformance.runner import ConformanceError, load_lock, report, verify_standard_checkout


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def repository(tmp_path: Path) -> tuple[Path, str]:
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.email", "tests@example.invalid")
    git(tmp_path, "config", "user.name", "DTC Tests")
    git(tmp_path, "remote", "add", "origin", "https://github.com/SEH-OS/DTC-Standard.git")
    (tmp_path / "README.md").write_text("test\n", encoding="utf-8")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-m", "test")
    return tmp_path, git(tmp_path, "rev-parse", "HEAD")


def test_lock_is_exact() -> None:
    lock = load_lock(Path(__file__).parents[1] / "dtc-standard.lock.json")
    assert lock["tag"] == "v0.3.0-rc.2"
    assert lock["commit"] == "57912cc546c7d8d9b4cf0ef9a176a95c59e11063"


def test_checkout_accepts_exact_clean_commit(tmp_path: Path) -> None:
    root, commit = repository(tmp_path)
    assert verify_standard_checkout(root, commit, "https://github.com/SEH-OS/DTC-Standard.git") == commit


def test_checkout_rejects_wrong_commit(tmp_path: Path) -> None:
    root, _ = repository(tmp_path)
    with pytest.raises(ConformanceError, match="standard-commit-mismatch"):
        verify_standard_checkout(root, "0" * 40, "https://github.com/SEH-OS/DTC-Standard.git")


def test_checkout_rejects_dirty_state(tmp_path: Path) -> None:
    root, commit = repository(tmp_path)
    (root / "README.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ConformanceError, match="standard-worktree-not-clean"):
        verify_standard_checkout(root, commit, "https://github.com/SEH-OS/DTC-Standard.git")


def test_checkout_rejects_wrong_origin(tmp_path: Path) -> None:
    root, commit = repository(tmp_path)
    with pytest.raises(ConformanceError, match="standard-origin-mismatch"):
        verify_standard_checkout(root, commit, "https://github.com/example/not-the-standard.git")


def test_report_is_explicitly_non_certifying(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    evidence = report(
        mode="instance",
        standard_commit="a" * 40,
        standard_tag="v0.3.0-rc.2",
        outcome="pass",
        command=["validator"],
        target=target,
        process=subprocess.CompletedProcess(["validator"], 0, "ok", ""),
    )
    assert evidence["claim_type"] == "self_assessment_test_evidence"
    assert "not a certification" in evidence["limitations"][0]
    assert evidence["target"]["sha256"]
    assert evidence["generated_at"].endswith("Z")
    assert evidence["harness"]["version"] == "0.1.0rc1"
