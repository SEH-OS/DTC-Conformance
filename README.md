# DTC Conformance

Official, fail-closed test harness for pinned releases of the Digital Twin Core
Standard. This repository is separate from the normative standard and from any
runtime implementation.

The harness verifies the exact Standard commit, rejects dirty or mismatched
checkouts, runs the complete Standard gate, validates one of the five completed
profile instance types, and emits a machine-readable Conformance Claim aligned
with the Standard's `conformance-claim.schema.json` contract.

It does **not** issue certificates or prove that claims are true, that a system
is secure, or that an organization is compliant with law or donor obligations.

## Usage

```bash
python -m pip install -e .
dtc-conformance standard --standard-root ../DTC-Standard --output report.json
dtc-conformance instance --standard-root ../DTC-Standard \
  --profile organization --input twin.json --output report.json
dtc-conformance document --standard-root ../DTC-Standard \
  --schema core-event --input accepted-event.json --output event-report.json
```

Release validation uses the lock file by default. A pre-release integration
workflow MAY validate exact unreleased bytes by supplying the full current SHA:

```bash
dtc-conformance standard --standard-root ../DTC-Standard \
  --candidate-commit 0123456789abcdef0123456789abcdef01234567 \
  --output candidate-report.json
```

Candidate mode still verifies origin, exact HEAD and a clean worktree; its
report tag is `unreleased-candidate`. It is not a substitute for a tagged
release report. Document mode also supports `interoperability-mapping`.

The currently pinned standard is `SEH-OS/DTC-Standard@v0.3.0-rc.2`. Reports
identify the exact commit, command, target digest, outcome and limitations.

Hosted exact-pin integration is orchestrated from the private Standard
repository and publishes the resulting reports there. Unit CI in this public
repository is not a substitute for that integration gate.

## Development gate

```bash
make check
```
