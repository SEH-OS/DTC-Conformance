# Changelog

## Unreleased

- Replaced the harness-specific evidence envelope with the Standard's unified
  Conformance Claim 0.1 contract while preserving exact revision, target digest,
  procedure outcome and explicit non-certification limitations.
- Self-assessment now records the harness as a contributing, non-independent
  evaluator and fixes certification status to `not_certified`.

## 0.1.0-rc.3 - 2026-08-30

- Added schema-mode validation for DTC interoperability mapping manifests.
- Added explicit exact-SHA candidate mode for pre-release integration without
  weakening the default release lock.
- Preserved fail-closed origin, clean-worktree and exact-HEAD verification and
  labelled candidate evidence as `unreleased-candidate`.

## 0.1.0-rc.2 - 2026-08-30

- Added document validation for Candidate, PolicyDecision, CoreEvent,
  IntegrityProof and conformant GraphSnapshot artifacts.
