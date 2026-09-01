from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from dtc_conformance.cli import parser
from dtc_conformance.runner import ConformanceError, DOCUMENT_SCHEMAS, candidate_semantic_errors, execute_document_validation, graph_semantic_errors, integrity_proof_semantic_errors, load_lock, report, verify_standard_checkout


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
    assert evidence["subject"]["artifact_digest"]
    assert evidence["generated_at"].endswith("Z")
    assert evidence["suite"]["repository"].endswith("DTC-Conformance")
    assert evidence["certification_status"] == "not_certified"


def test_interoperability_mapping_schema_is_exposed() -> None:
    assert DOCUMENT_SCHEMAS["interoperability-mapping"] == "interoperability-mapping.schema.json"
    parsed = parser().parse_args([
        "document", "--standard-root", ".", "--candidate-commit", "a" * 40,
        "--schema", "interoperability-mapping", "--input", "mapping.json",
        "--output", "report.json",
    ])
    assert parsed.candidate_commit == "a" * 40
    assert parsed.schema == "interoperability-mapping"


def test_document_validation_passes_and_fails_closed(tmp_path: Path) -> None:
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://example.invalid/test.schema.json", "type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}, "additionalProperties": False}
    (schemas / "candidate.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    valid = tmp_path / "valid.json"
    valid.write_text('{"id":"candidate-1"}', encoding="utf-8")
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"id":1}', encoding="utf-8")
    assert execute_document_validation(tmp_path, "candidate", valid).returncode == 0
    assert execute_document_validation(tmp_path, "candidate", invalid).returncode == 1


def test_document_validation_enforces_formats(tmp_path: Path) -> None:
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://example.invalid/test.schema.json", "type": "object", "required": ["created_at"], "properties": {"created_at": {"type": "string", "format": "date-time"}}}
    (schemas / "candidate.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    invalid = tmp_path / "invalid-time.json"
    invalid.write_text('{"created_at":"not-a-date-time"}', encoding="utf-8")
    assert execute_document_validation(tmp_path, "candidate", invalid).returncode == 1


def test_graph_semantics_reject_dangling_and_cross_tenant() -> None:
    graph = {
        "tenant_id": "tenant-1",
        "scope_id": "scope-1",
        "objects": [
            {"id": "one", "tenant_id": "tenant-1", "scope_id": "scope-1"},
            {"id": "two", "tenant_id": "tenant-2", "scope_id": "scope-1"},
        ],
        "relationships": [{"id": "rel", "source_object_id": "one", "target_object_id": "missing", "tenant_id": "tenant-1", "scope_id": "scope-1"}],
    }
    errors = graph_semantic_errors(graph)
    assert any("unresolved" in error for error in errors)
    assert any("tenant_id" in error for error in errors)


def test_core_semantics_fail_closed() -> None:
    assert candidate_semantic_errors({"status": "rejected"})
    assert candidate_semantic_errors({"status": "accepted", "accepted_event_id": "a", "policy_decision_id": "d", "transition_history": [{"from_status": "proposed", "to_status": "accepted", "accepted_event_id": "b", "policy_decision_id": "d"}]})
    assert integrity_proof_semantic_errors({"proof_type": "event_stream", "applicable_checks": ["canonical_digest"], "checks": [{"check_type": "canonical_digest", "status": "pass"}]})


def test_graph_semantics_reject_reversed_time() -> None:
    graph = {"tenant_id": "tenant-1", "scope_id": "scope-1", "objects": [{"id": "one", "tenant_id": "tenant-1", "scope_id": "scope-1", "valid_from": "2026-08-22T00:00:00Z", "valid_to": "2026-08-21T00:00:00Z"}], "relationships": []}
    assert any("valid_to" in error for error in graph_semantic_errors(graph))
