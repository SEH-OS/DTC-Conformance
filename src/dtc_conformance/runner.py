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

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from . import __version__


PROFILE_SCRIPTS = {
    "organization": "validate_organization_twin.py",
    "project": "validate_project_twin.py",
    "donor-funder": "validate_donor_funder_twin.py",
    "product": "validate_product_twin.py",
    "verified-impact": "validate_verified_impact_twin.py",
}
DOCUMENT_SCHEMAS = {
    "candidate": "candidate.schema.json",
    "policy-decision": "policy-decision.schema.json",
    "core-event": "core-event.schema.json",
    "integrity-proof": "integrity-proof.schema.json",
    "graph-snapshot": "graph-snapshot.conformant.schema.json",
    "interoperability-mapping": "interoperability-mapping.schema.json",
}
EVENT_STREAM_CHECKS = {"canonical_digest", "stream_continuity", "signature", "policy_validity", "decision_replay", "obligation_satisfaction", "evidence_integrity", "projection_consistency"}


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


def execute_document_validation(
    standard_root: Path, schema_name: str, document_path: Path
) -> subprocess.CompletedProcess[str]:
    try:
        filename = DOCUMENT_SCHEMAS[schema_name]
    except KeyError as exc:
        raise ConformanceError(f"unsupported-document-schema:{schema_name}") from exc
    if not document_path.is_file():
        raise ConformanceError("document-not-found")
    schemas = standard_root / "schemas"
    resources = []
    try:
        for path in schemas.glob("*.schema.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            resources.append((document["$id"], Resource.from_contents(document)))
        schema = json.loads((schemas / filename).read_text(encoding="utf-8"))
        instance = json.loads(document_path.read_text(encoding="utf-8"))
        errors = sorted(
            Draft202012Validator(schema, registry=Registry().with_resources(resources), format_checker=FormatChecker()).iter_errors(instance),
            key=lambda item: list(item.absolute_path),
        )
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        return subprocess.CompletedProcess(["document-validator", schema_name, str(document_path)], 1, "", f"document-validation-error:{exc}")
    if errors:
        output = "\n".join(f"{'/'.join(map(str, error.absolute_path))}:{error.message}" for error in errors)
        return subprocess.CompletedProcess(["document-validator", schema_name, str(document_path)], 1, "", output)
    semantic_errors: list[str] = []
    if schema_name == "graph-snapshot":
        semantic_errors = graph_semantic_errors(instance)
    elif schema_name == "candidate" and "status" in instance:
        semantic_errors = candidate_semantic_errors(instance)
    elif schema_name == "integrity-proof":
        semantic_errors = integrity_proof_semantic_errors(instance)
    if semantic_errors:
        return subprocess.CompletedProcess(["document-validator", schema_name, str(document_path)], 1, "", "\n".join(semantic_errors))
    return subprocess.CompletedProcess(["document-validator", schema_name, str(document_path)], 0, f"document=ok schema={schema_name}\n", "")


def graph_semantic_errors(snapshot: dict[str, Any]) -> list[str]:
    """Enforce cross-record graph invariants outside JSON Schema."""
    objects = snapshot.get("objects", [])
    relationships = snapshot.get("relationships", [])
    object_ids = [item.get("id") for item in objects]
    relationship_ids = [item.get("id") for item in relationships]
    errors: list[str] = []
    if len(object_ids) != len(set(object_ids)):
        errors.append("object ids must be unique")
    if len(relationship_ids) != len(set(relationship_ids)):
        errors.append("relationship ids must be unique")
    known_objects = set(object_ids)
    for item in objects + relationships:
        for error in temporal_semantic_errors(item):
            errors.append(f"{item.get('id', '<unknown>')}: {error}")
    for relationship in relationships:
        for endpoint in ("source_object_id", "target_object_id"):
            if relationship.get(endpoint) not in known_objects:
                errors.append(f"relationship {relationship.get('id', '<unknown>')} has unresolved {endpoint}")
    tenant_ids = {item.get("tenant_id") for item in objects + relationships}
    scope_ids = {item.get("scope_id") for item in objects + relationships}
    if tenant_ids and tenant_ids != {snapshot.get("tenant_id")}:
        errors.append("graph tenant_id must equal snapshot tenant_id")
    if scope_ids and scope_ids != {snapshot.get("scope_id")}:
        errors.append("graph scope_id must equal snapshot scope_id")
    return errors


def temporal_semantic_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for start_name, end_name in (("valid_from", "valid_to"), ("tx_from", "tx_to")):
        if record.get(start_name) and record.get(end_name):
            start = datetime.fromisoformat(record[start_name].replace("Z", "+00:00"))
            end = datetime.fromisoformat(record[end_name].replace("Z", "+00:00"))
            if end < start:
                errors.append(f"{end_name} must not precede {start_name}")
    return errors


def candidate_semantic_errors(candidate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    history = candidate.get("transition_history", [])
    status = candidate.get("status")
    if status != "proposed" and not history:
        return ["a non-proposed candidate requires transition_history"]
    previous = "proposed"
    for index, transition in enumerate(history):
        if transition.get("from_status") != previous:
            errors.append(f"transition_history[{index}] is not contiguous")
        previous = transition.get("to_status")
    if history and previous != status:
        errors.append("the final transition status must equal candidate status")
    if status == "accepted" and history:
        final = history[-1]
        for field in ("policy_decision_id", "accepted_event_id"):
            if final.get(field) != candidate.get(field):
                errors.append(f"accepted transition {field} must equal candidate {field}")
    return errors


def integrity_proof_semantic_errors(proof: dict[str, Any]) -> list[str]:
    applicable = proof.get("applicable_checks", [])
    check_types = [check.get("check_type") for check in proof.get("checks", [])]
    errors: list[str] = []
    if len(check_types) != len(set(check_types)):
        errors.append("each applicable integrity check must appear exactly once")
    if set(check_types) != set(applicable):
        errors.append("checks must exactly cover applicable_checks")
    if proof.get("proof_type") == "event_stream" and set(applicable) != EVENT_STREAM_CHECKS:
        errors.append("event_stream proofs require the complete check set")
    return errors


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
