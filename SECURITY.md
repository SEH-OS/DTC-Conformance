# Security policy

Report vulnerabilities privately through GitHub Security Advisories for this
repository. Do not include credentials, personal data or live client artifacts
in issues, fixtures or conformance reports.

The harness executes validation code from the exactly pinned DTC Standard
checkout. Run it only against a trusted checkout whose origin, commit and clean
state pass the built-in preconditions.

Hosted integration remains disabled until the pinned Standard release is
publicly readable or an organization-approved read-only access mechanism is
available. A broad personal token MUST NOT be used to bypass that boundary.
