# FluxRules GAPS 

## What does exist?

- Clear BRMS service split between full all-vs-all and incremental candidate validation modes, with explicit intended complexity guidance in code comments/docstrings. 

- Incremental write-path validation is wired in service layer and used in runtime flow. 

- Packaging moved toward installable distribution (name = "fluxrules", build backend present, extras for dev/docs). 

- Documentation now includes migration/run/test guidance and API-only mode operation. 

- Backend/frontend coupling is reduced by optional frontend serving toggle. 

- Security defaults are not enterprise-safe

- Static default JWT secret in config. 

- Default seeded admin user/password (admin / admin123). 

- Wide-open CORS (* origins, methods, headers). 

- Migration framework (Alembic-style)
- Governance/compliance (P1)
Add migration/versioning policy for schema/rules, audit immutability controls, retention policies.


## Current gaps

- HA concerns

- DB fallback silently degrades to local SQLite when primary DB is unavailable (good for dev, risky for production determinism). 

- Bulk validation worker is in-process thread pool + in-memory job registry (no durable queue/state across restarts). 

- Validation completeness vs scale trade-off remains unresolved operationally

- Full mode runs deeper checks (including SAT/redundancy/gap). 

- Candidate mode is optimized but intentionally narrower. 

- A production policy for scheduled full-audit runs and reporting (partially available)


## TO DO Next

What to do next (priority order)

Operational durability (P0)
Move async jobs to durable queue + persistent job store.

Validation strategy (P1)
Keep candidate checks synchronous; run full checks on schedule and expose report status in API.

Release/quality gates (P1)
CI: lint/type/tests/build/docs strict + signed artifacts + staged deployments.
