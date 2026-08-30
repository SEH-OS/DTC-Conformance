# DTC Conformance

Official, fail-closed test harness for pinned releases of the Digital Twin Core
Standard. This repository is separate from the normative standard and from any
runtime implementation.

The harness verifies the exact Standard commit, rejects dirty or mismatched
checkouts, runs the complete Standard gate, validates one of the five completed
profile instance types, and emits a machine-readable evidence report.

It does **not** issue certificates or prove that claims are true, that a system
is secure, or that an organization is compliant with law or donor obligations.

## Usage

```bash
python -m pip install -e .
dtc-conformance standard --standard-root ../DTC-Standard --output report.json
dtc-conformance instance --standard-root ../DTC-Standard \
  --profile organization --input twin.json --output report.json
```

The currently pinned standard is `SEH-OS/DTC-Standard@v0.3.0-rc.2`. Reports
identify the exact commit, command, target digest, outcome and limitations.

## Development gate

```bash
make check
```
