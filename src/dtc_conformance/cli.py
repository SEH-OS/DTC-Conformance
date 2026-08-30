"""Command-line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

from .runner import (
    ConformanceError,
    current_harness_commit,
    execute_profile_validation,
    execute_standard_gate,
    load_lock,
    report,
    verify_standard_checkout,
)


ROOT = Path(__file__).resolve().parents[2]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="dtc-conformance")
    result.add_argument("mode", choices=("standard", "instance"))
    result.add_argument("--standard-root", type=Path, required=True)
    result.add_argument("--profile", choices=("organization", "project", "donor-funder", "product", "verified-impact"))
    result.add_argument("--input", type=Path)
    result.add_argument("--output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    lock = load_lock(ROOT / "dtc-standard.lock.json")
    process = None
    target = None
    command: list[str] = []
    failure = None
    try:
        commit = verify_standard_checkout(args.standard_root.resolve(), lock["commit"], lock["repository"])
        if args.mode == "standard":
            command = ["make", "check"]
            process = execute_standard_gate(args.standard_root.resolve())
        else:
            if not args.profile or not args.input:
                raise ConformanceError("instance-requires-profile-and-input")
            target = args.input.resolve()
            command = ["profile-validator", args.profile, str(target)]
            process = execute_profile_validation(args.standard_root.resolve(), args.profile, target)
        command = [str(item) for item in process.args]
        outcome = "pass" if process.returncode == 0 else "fail"
        if process.returncode:
            failure = "validation-command-failed"
    except ConformanceError as exc:
        commit = lock["commit"]
        outcome = "fail"
        failure = str(exc)
    evidence = report(
        mode=args.mode,
        standard_commit=commit,
        standard_tag=lock["tag"],
        outcome=outcome,
        command=command,
        target=target,
        process=process,
        failure=failure,
        harness_commit=current_harness_commit(ROOT),
    )
    schema = json.loads((ROOT / "schemas/conformance-report.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(evidence)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return 0 if outcome == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
