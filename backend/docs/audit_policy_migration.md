# FluxRules — Production Audit Policy: Migration & Operations Guide

## Overview

This guide covers the **scheduled full-audit** feature added in FluxRules 1.1.0.
It enables production deployments to run automated, periodic audit sweeps that
verify data integrity, enforce retention policies, compute rule coverage, and
report rule health — all with immutable, tamper-proof audit reports.

**All changes are backward-compatible.** Existing APIs, schemas, and behaviour
are preserved when using default settings.

---

## Quick Start (Existing Deployments)

```bash
cd backend
source .venv/bin/activate

# 1. Apply the new migration (adds audit_policies and audit_reports tables)
alembic upgrade head

# 2. Add new settings to your .env file (all optional — sane defaults)
cat >> .env << 'EOF'
# Enable the background audit scheduler (default: false)
AUDIT_SCHEDULER_ENABLED=true
EOF

# 3. Restart the service
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **Note:** If you skip the `alembic upgrade head` step, the tables are still
> created automatically by `Base.metadata.create_all()` on startup. However,
> running Alembic is recommended for production so that version tracking
> remains consistent.

---

## What Changed

### New Database Tables (Additive Only)

| Table | Purpose |
|-------|---------|
| `audit_policies` | Stores configurable audit-policy definitions with cron schedules |
| `audit_reports` | Immutable records of every audit-run execution |

No existing tables are modified. The migration (`002_add_audit_policies_and_reports`)
is purely additive.

### New Configuration Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `AUDIT_SCHEDULER_ENABLED` | `false` | Enable the background scheduler daemon thread |

All existing settings (`AUDIT_RETENTION_DAYS`, `AUDIT_INTEGRITY_ENABLED`, etc.)
continue to work exactly as before and are consumed by the audit runner.

### New API Endpoints

All under `/api/v1/admin/` (admin-only):

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/admin/audit-policy` | Create a new audit policy |
| `GET` | `/admin/audit-policy` | List all audit policies |
| `GET` | `/admin/audit-policy/{id}` | Get a single policy |
| `PATCH` | `/admin/audit-policy/{id}` | Update a policy |
| `DELETE` | `/admin/audit-policy/{id}` | Delete a policy |
| `POST` | `/admin/audit-run` | Trigger a manual audit run |
| `GET` | `/admin/audit-report` | List audit reports |
| `GET` | `/admin/audit-report/{id}` | Get full report details |

### Existing Endpoints (Unchanged)

All existing endpoints continue to work identically:

- `GET /api/v1/admin/audit/integrity` — spot-check integrity hashes
- `POST /api/v1/admin/audit/retention` — apply retention policy
- `GET /api/v1/admin/schema` — schema version info
- `GET /api/v1/admin/db/health` — database health diagnostics
- `GET /health` — lightweight health probe

---

## Architecture

### System Overview

```
                          ┌─────────────────────────────────┐
                          │        FluxRules Server         │
                          │         (FastAPI + SQLite)      │
                          └───────────────┬─────────────────┘
                                          │
               ┌──────────────────────────┼──────────────────────────┐
               │                          │                          │
               ▼                          ▼                          ▼
  ┌────────────────────┐   ┌────────────────────┐   ┌────────────────────────┐
  │   Audit Policies   │   │    Audit Runner    │   │    Audit Reports       │
  │                    │   │                    │   │                        │
  │ • name             │──▶│ • integrity check  │──▶│ • status (passed/warn/ │
  │ • cron_expression  │   │ • retention purge  │   │   error)               │
  │ • scope            │   │ • coverage calc    │   │ • details_json         │
  │ • enabled          │   │ • rule_health scan │   │ • integrity_hash       │
  │ • next_run_at      │   │ • performance bench│   │ • duration_seconds     │
  └────────────────────┘   └─────────┬──────────┘   │ • triggered_by         │
               ▲                     │              └────────────────────────┘
               │                     │                          │
       ┌───────┴────────┐           │                          ▼
       │                │           ▼                 ┌──────────────────┐
       │  Two Triggers  │  ┌──────────────────┐      │   audit_logs     │
       │                │  │  Meta-Audit Log   │      │   (append-only)  │
       │ 1. Background  │  │  action_type=     │      └──────────────────┘
       │    Scheduler   │  │  "audit_run"      │
       │ 2. Manual API  │  └──────────────────┘
       └────────────────┘
```

### Data Flow: End-to-End

```
 Admin creates policy ──▶ Policy saved with computed next_run_at
                                     │
             ┌───────────────────────┤
             ▼                       ▼
     ┌───────────────┐      ┌────────────────┐
     │  Background    │      │  Manual API     │
     │  Scheduler     │      │  POST /admin/   │
     │  (daemon       │      │  audit-run      │
     │   thread,      │      │  {scope: "all"} │
     │   60s tick)    │      └───────┬─────────┘
     └───────┬────────┘              │
             │ checks:               │
             │ next_run_at <= now?   │
             │ enabled == true?      │
             ▼                       ▼
     ┌────────────────────────────────────────────┐
     │             Audit Runner                    │
     │                                             │
     │  1. Resolve scopes from scope string        │
     │  2. Execute each check (integrity,          │
     │     retention, coverage, rule_health,       │
     │     performance)                            │
     │  3. Aggregate results into JSON             │
     │  4. Compute HMAC-SHA256 integrity hash      │
     │  5. Persist immutable AuditReport row       │
     │  6. Write meta-audit entry to audit_logs    │
     │  7. Update policy.last_run_at if scheduled  │
     │  8. Recompute policy.next_run_at from cron  │
     └──────────────────────┬─────────────────────┘
                            │
                            ▼
     ┌────────────────────────────────────────────┐
     │       AuditReport (immutable row)           │
     │                                             │
     │  id: 42                                     │
     │  scope: "all"                               │
     │  status: "passed"                           │
     │  summary: "5 checks executed in 0.01s"      │
     │  details_json: { integrity: {...},          │
     │                   retention: {...},          │
     │                   coverage: {...},           │
     │                   rule_health: {...},        │
     │                   performance: {...} }       │
     │  integrity_hash: "9565b158959441af..."      │
     │  triggered_by: "manual" | "schedule"        │
     │  executed_at: "2026-03-26T02:00:00"         │
     └────────────────────────────────────────────┘
```

### Audit Scopes

Each audit run executes one or more **scopes** (comma-separated or `"all"`):

| Scope | What It Does | Key Metrics Returned |
|-------|-------------|----------------------|
| `integrity` | Verifies HMAC-SHA256 hashes on up to 500 recent audit-log rows | `total_checked`, `valid`, `invalid`, `unprotected` |
| `retention` | Applies the configured `AUDIT_RETENTION_DAYS` purge policy | `retention_days`, `rows_purged` |
| `coverage` | Computes rule-coverage metrics (enabled vs. triggered rules) | `total_rules`, `enabled_rules`, `coverage_pct`, `never_fired_rule_ids` |
| `rule_health` | Checks for disabled rules, missing descriptions, missing groups | `total_rules`, `disabled_count`, `issues[]` |
| `performance` | Benchmarks audit-query latency (count, integrity-check timings) | `audit_log_count`, `*_query_ms` |
| `all` | Runs every check above | All of the above combined |

---

### Two Ways to Generate Reports

#### Way 1 — Manual Run (Instant, On-Demand)

Trigger an ad-hoc audit from the API at any time. The response includes the
full report inline. No policy or scheduler required.

```
POST /api/v1/admin/audit-run
Authorization: Bearer <admin-token>

{
  "scope": "all"                    ← or "integrity", "coverage,rule_health", etc.
  "policy_id": null                 ← optional: link to an existing policy
}
```

**Response (immediate):**

```json
{
  "report_id": 1,
  "status": "passed",
  "summary": "5 checks executed in 0.01s",
  "details": {
    "integrity":  { "total_checked": 500, "valid": 490, "invalid": 0, "unprotected": 10 },
    "retention":  { "retention_days": 90, "rows_purged": 0 },
    "coverage":   { "total_rules": 28, "enabled_rules": 28, "coverage_pct": 75.0, ... },
    "rule_health":{ "total_rules": 28, "disabled_count": 0, "issues": [] },
    "performance":{ "audit_log_count": 2655, "audit_count_query_ms": 2.14, ... }
  }
}
```

Use this for:

- Pre-deployment validation ("are all rules healthy?")
- Incident investigation ("has anything been tampered with?")
- One-off compliance checks

#### Way 2 — Scheduled Run (Automatic, Cron-Based)

Create an audit policy with a cron schedule. The background scheduler daemon
thread evaluates all enabled policies every 60 seconds, runs any that are due,
and persists the report automatically.

**Step 1 — Enable the scheduler** (once, in `.env`):

```bash
AUDIT_SCHEDULER_ENABLED=true
```

**Step 2 — Create a policy:**

```
POST /api/v1/admin/audit-policy
Authorization: Bearer <admin-token>

{
  "name": "Nightly Full Audit",
  "description": "Runs ALL checks every night at 2 AM UTC",
  "cron_expression": "0 2 * * *",
  "scope": "all",
  "enabled": true
}
```

**What happens at 2:00 AM every day:**

```
 ┌─ Scheduler tick (every 60s) ─────────────────────────────────────┐
 │                                                                   │
 │  1. Query: SELECT * FROM audit_policies                           │
 │            WHERE enabled=true AND next_run_at <= NOW()            │
 │                                                                   │
 │  2. For each due policy:                                          │
 │     a. AuditRunner.execute(scope=policy.scope,                    │
 │                             policy_id=policy.id,                  │
 │                             triggered_by="schedule")              │
 │     b. Persist AuditReport (immutable)                            │
 │     c. Set policy.last_run_at = NOW()                             │
 │     d. Recompute policy.next_run_at from cron expression          │
 │                                                                   │
 │  3. Commit all changes                                            │
 └───────────────────────────────────────────────────────────────────┘
```

Use this for:

- Continuous compliance monitoring
- Nightly integrity sweeps
- Recurring retention enforcement
- Automated rule-health dashboards

#### Reading Reports (Both Ways)

Reports from both manual and scheduled runs land in the same `audit_reports`
table and are queried through the same endpoints:

```bash
# List all reports (newest first, max 50)
GET /api/v1/admin/audit-report

# Filter by status
GET /api/v1/admin/audit-report?status=passed
GET /api/v1/admin/audit-report?status=warnings

# Filter by policy (scheduled runs only)
GET /api/v1/admin/audit-report?policy_id=1

# Get full details (includes raw JSON + integrity hash)
GET /api/v1/admin/audit-report/{id}
```

The `triggered_by` field on each report tells you whether it came from
`"schedule"` or `"manual"`.

---

### Immutable Reports

Every audit run (scheduled or manual) produces an `AuditReport` row with:

- **Structured JSON details** for each scope executed
- **HMAC-SHA256 integrity hash** computed over `scope|status|details_json|executed_at` — prevents post-hoc tampering
- **Aggregate metrics:** duration, coverage %, rule count, violation count, purge count
- **`triggered_by` flag:** `"schedule"` or `"manual"`

Reports are **append-only** — there are no update or delete endpoints.
Any modification to the underlying row will invalidate the `integrity_hash`.

### Meta-Audit Trail

Each audit run also creates an entry in the `audit_logs` table
(`action_type="audit_run"`), so the audit system itself is fully auditable.

---

## Cron Expression Reference

The built-in scheduler supports standard 5-field cron syntax:

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, 0=Sunday)
│ │ │ │ │
* * * * *
```

Examples:

| Expression | Description |
|-----------|-------------|
| `0 2 * * *` | Every day at 2:00 AM |
| `0 */6 * * *` | Every 6 hours |
| `30 1 * * 1` | Every Monday at 1:30 AM |
| `0 0 1 * *` | First day of every month at midnight |
| `*/15 * * * *` | Every 15 minutes |

---

## API Usage Examples

### Create an Audit Policy

```bash
curl -X POST http://localhost:8000/api/v1/admin/audit-policy \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "nightly-full-audit",
    "description": "Full audit sweep every night at 2 AM",
    "cron_expression": "0 2 * * *",
    "scope": "all",
    "enabled": true
  }'
```

### Trigger a Manual Run

```bash
curl -X POST http://localhost:8000/api/v1/admin/audit-run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scope": "integrity,coverage"}'
```

### List Recent Reports

```bash
curl http://localhost:8000/api/v1/admin/audit-report?limit=10 \
  -H "Authorization: Bearer $TOKEN"
```

### Get Full Report Details

```bash
curl http://localhost:8000/api/v1/admin/audit-report/1 \
  -H "Authorization: Bearer $TOKEN"
```

---

## Migration Steps (Detailed)

### For Existing Deployments

1. **Update code** — pull the latest version.

2. **Run database migration:**
   ```bash
   cd backend
   source .venv/bin/activate
   alembic upgrade head
   ```
   This creates the `audit_policies` and `audit_reports` tables.

3. **Configure environment** (optional):
   ```bash
   # Enable scheduled audits
   AUDIT_SCHEDULER_ENABLED=true

   # Existing settings continue to work as-is:
   AUDIT_RETENTION_DAYS=90
   AUDIT_INTEGRITY_ENABLED=true
   ```

4. **Restart the service.**

5. **Create your first policy** via the API or admin UI.

### For New Deployments

No special steps needed. The tables are created automatically on first startup.
Optionally enable the scheduler via `AUDIT_SCHEDULER_ENABLED=true`.

### Rollback

To roll back the migration:

```bash
alembic downgrade 977895da9fbe
```

This drops only the `audit_policies` and `audit_reports` tables — no existing
data is affected.

---

## Security Considerations

- **Report integrity:** All audit reports are stamped with HMAC-SHA256 hashes
  keyed by `SECRET_KEY`. Tampering with any report field (scope, status,
  details, timestamp) will invalidate the hash.

- **Admin-only access:** All audit-policy and audit-report endpoints require
  admin authentication via the existing `get_current_admin` dependency.

- **Meta-audit trail:** The audit system audits itself — every run creates an
  `audit_logs` entry with `action_type="audit_run"`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Scheduler not running | `AUDIT_SCHEDULER_ENABLED` is `false` (default) | Set to `true` in `.env` |
| Policy never executes | `enabled=false` or `next_run_at` in the future | Check policy via API |
| Migration fails | Alembic head not stamped | Run `alembic stamp head` first |
| Report shows "error" status | A check threw an exception | Check server logs |
| Integrity violations in report | Audit-log rows were tampered with | Investigate — this is a security event |
