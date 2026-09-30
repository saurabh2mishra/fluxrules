# Security Policy

## Supported Versions

FluxRules is pre-1.0 and unpublished (`0.0.x`). Security fixes are applied to the
latest development line; there are no long-term-support branches yet.

| Version | Supported |
|---------|-----------|
| `0.0.x` | :white_check_mark: (current development line) |
| `< 0.0.1` | :x: |

When `1.0` is released this table will be updated with the LTS policy.

## Reporting a Vulnerability

Do not open public issues, pull requests, or discussions for potential
vulnerabilities.

Please report security issues privately through GitHub Security Advisories:

- https://github.com/fluxrules/fluxrules/security/advisories/new

Include:

- affected version or commit
- impact summary (what an attacker can do)
- reproduction steps or a proof of concept
- any known mitigations or workarounds

### Response targets

These are targets, not contractual guarantees, for a volunteer-maintained
project:

| Stage | Target |
|-------|--------|
| Acknowledge receipt | within **3 business days** |
| Initial assessment / severity triage | within **7 business days** |
| Fix or documented mitigation for High/Critical | within **30 days** of triage |
| Coordinated public disclosure | after a fix ships, or **90 days** after report, whichever is sooner |

We follow **coordinated disclosure**: we agree on a disclosure date with the
reporter and credit reporters who wish to be named in the advisory and release
notes.

## Security Notes for Operators

- Validate and control who can create or modify rules — rule authors are a
  trust boundary (see the threat model in `docs/security.md`).
- Protect API deployments with authentication and network restrictions; the API
  ships auth primitives but enforces no auth by default.
- Override the default `SECRET_KEY` via environment configuration before
  exposing the API.
- Keep dependencies updated, especially the optional `api` and persistence
  extras; Dependabot and the CI `security` job (bandit + pip-audit) help track
  this.
- Review logs and traces for suspicious rule changes or evaluation spikes.
- Dependency triage status for the optional API extra: the project requires a
  patched Starlette release and uses PyJWT instead of `python-jose` to avoid its
  ECDSA dependency path. A clean non-editable API-extra install audited without
  known findings on 2026-09-30; CI repeats that extra-specific audit.
