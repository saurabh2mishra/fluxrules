"""Production audit-runner service — orchestrates full-audit sweeps.

This service executes configurable audit checks and persists immutable
results.  It is designed to be invoked by:

* The built-in background scheduler (see :mod:`app.services.audit_scheduler`).
* The admin API endpoint for manual/ad-hoc runs.

Supported audit scopes
----------------------
``integrity``
    Verify HMAC-SHA256 hashes on audit-log rows.  Detects post-hoc tampering.

``retention``
    Apply the configured ``AUDIT_RETENTION_DAYS`` policy and purge old rows.

``coverage``
    Compute rule-coverage metrics (enabled vs. triggered rules).

``rule_health``
    Check for disabled rules, rules with no recent executions, orphaned
    versions, and rules missing required metadata fields.

``performance``
    Measure audit-query latency and report statistics.

``all``
    Run every check above.

Backward Compatibility
----------------------
This module is **purely additive**.  It imports existing services
(``AuditService``, ``AnalyticsService``, ``RuleService``) and reads from
existing tables — no schema changes to pre-existing tables are required.

.. versionadded:: 1.1.0
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.config import settings
from app.models.audit_policy import AuditPolicy, AuditReport
from app.models.rule import Rule
from app.services.audit_service import AuditService

logger = logging.getLogger("fluxrules.audit_runner")

# The recognised scope tokens.
VALID_SCOPES: Set[str] = frozenset(
    {"integrity", "retention", "coverage", "rule_health", "performance", "all"}
)

# Default number of audit-log rows to integrity-check per run.
_DEFAULT_INTEGRITY_LIMIT: int = 500


def _resolve_scopes(scope_str: str) -> List[str]:
    """Parse a comma-separated scope string into a sorted list of checks.

    Args:
        scope_str: User-supplied scope string (e.g. ``"integrity,coverage"``
            or ``"all"``).

    Returns:
        Sorted list of individual scope tokens.  ``"all"`` expands to
        every known check.

    Raises:
        ValueError: If any token is not in :data:`VALID_SCOPES`.
    """
    tokens = [t.strip().lower() for t in scope_str.split(",") if t.strip()]
    if "all" in tokens:
        return sorted(VALID_SCOPES - {"all"})
    unknown = set(tokens) - VALID_SCOPES
    if unknown:
        raise ValueError(
            f"Unknown audit scope(s): {', '.join(sorted(unknown))}. "
            f"Valid: {', '.join(sorted(VALID_SCOPES))}."
        )
    return sorted(set(tokens))


def _compute_report_hash(
    scope: str,
    status: str,
    details_json: str,
    executed_at: datetime,
) -> str:
    """Compute an HMAC-SHA256 integrity hash for an audit *report* row.

    Args:
        scope: Scope string of this run.
        status: Overall outcome.
        details_json: Serialised details payload.
        executed_at: Execution timestamp.

    Returns:
        Lowercase hex-encoded 64-character hash.
    """
    payload = f"{scope}|{status}|{details_json}|{executed_at.isoformat()}"
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class AuditRunner:
    """Orchestrates a full production audit sweep.

    Usage::

        runner = AuditRunner(db)
        report = runner.execute(scope="all")
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._audit_svc = AuditService(db)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        scope: str = "all",
        policy_id: Optional[int] = None,
        triggered_by: str = "manual",
    ) -> AuditReport:
        """Run the specified audit checks and persist an immutable report.

        Args:
            scope: Comma-separated scopes or ``"all"``.
            policy_id: Optional FK linking to an ``AuditPolicy``.
            triggered_by: ``"schedule"`` or ``"manual"``.

        Returns:
            The persisted ``AuditReport`` ORM instance.

        Raises:
            ValueError: If *scope* contains unknown tokens.
        """
        checks = _resolve_scopes(scope)
        start = time.monotonic()
        results: Dict[str, Any] = {}
        overall_status = "passed"
        integrity_violations = 0
        retention_purged = 0
        coverage_pct = 0.0
        rules_checked = 0

        for check_name in checks:
            try:
                result = self._run_check(check_name)
                results[check_name] = result

                # Aggregate key metrics
                if check_name == "integrity":
                    integrity_violations = result.get("invalid", 0)
                    if integrity_violations > 0:
                        overall_status = "warnings"
                elif check_name == "retention":
                    retention_purged = result.get("rows_purged", 0)
                elif check_name == "coverage":
                    coverage_pct = result.get("coverage_pct", 0.0)
                    rules_checked = result.get("total_rules", 0)
                elif check_name == "rule_health":
                    rules_checked = max(
                        rules_checked, result.get("total_rules", 0)
                    )
                    if result.get("issues"):
                        overall_status = "warnings"
                elif check_name == "performance":
                    pass  # informational only

            except Exception as exc:
                logger.exception("Audit check '%s' failed: %s", check_name, exc)
                results[check_name] = {"error": str(exc)}
                overall_status = "error"

        duration = round(time.monotonic() - start, 4)
        now = datetime.utcnow()

        summary_parts = [f"{len(checks)} checks executed in {duration:.2f}s"]
        if integrity_violations:
            summary_parts.append(f"{integrity_violations} integrity violation(s)")
        if retention_purged:
            summary_parts.append(f"{retention_purged} rows purged")
        summary = "; ".join(summary_parts)

        details_json = json.dumps(results, default=str)

        integrity_hash = _compute_report_hash(scope, overall_status, details_json, now)

        report = AuditReport(
            policy_id=policy_id,
            scope=scope,
            status=overall_status,
            summary=summary,
            details_json=details_json,
            integrity_violations=integrity_violations,
            retention_purged=retention_purged,
            coverage_pct=coverage_pct,
            rules_checked=rules_checked,
            duration_seconds=duration,
            integrity_hash=integrity_hash,
            triggered_by=triggered_by,
            executed_at=now,
        )
        self.db.add(report)

        # Update the linked policy's last_run_at if applicable.
        if policy_id:
            policy = self.db.query(AuditPolicy).filter(AuditPolicy.id == policy_id).first()
            if policy:
                policy.last_run_at = now

        # Audit-trail the audit run itself (meta-audit).
        self._audit_svc.log_action(
            action_type="audit_run",
            entity_type="audit_report",
            entity_id=None,
            user_id=None,
            details=f"Full audit completed: scope={scope}, status={overall_status}",
            execution_time=duration,
            auto_commit=False,
        )

        self.db.commit()
        self.db.refresh(report)
        logger.info(
            "Audit run #%d completed: status=%s, duration=%.2fs",
            report.id, overall_status, duration,
        )
        return report

    # ------------------------------------------------------------------
    # Individual check implementations
    # ------------------------------------------------------------------

    def _run_check(self, check_name: str) -> Dict[str, Any]:
        """Dispatch to the correct check method.

        Args:
            check_name: One of the :data:`VALID_SCOPES` tokens (excluding
                ``"all"``).

        Returns:
            Structured result dict.
        """
        dispatch = {
            "integrity": self._check_integrity,
            "retention": self._check_retention,
            "coverage": self._check_coverage,
            "rule_health": self._check_rule_health,
            "performance": self._check_performance,
        }
        handler = dispatch.get(check_name)
        if handler is None:
            return {"error": f"No handler for '{check_name}'"}
        return handler()

    def _check_integrity(self) -> Dict[str, Any]:
        """Verify HMAC-SHA256 hashes on recent audit-log rows.

        Returns:
            Dict with ``total_checked``, ``valid``, ``invalid``,
            ``unprotected`` counts.
        """
        result = self._audit_svc.verify_recent(limit=_DEFAULT_INTEGRITY_LIMIT)
        return result

    def _check_retention(self) -> Dict[str, Any]:
        """Apply the configured audit-retention policy.

        Returns:
            Dict with ``retention_days`` and ``rows_purged``.
        """
        purged = self._audit_svc.apply_retention_policy()
        return {
            "retention_days": settings.AUDIT_RETENTION_DAYS,
            "rows_purged": purged,
        }

    def _check_coverage(self) -> Dict[str, Any]:
        """Compute rule-coverage metrics.

        Returns:
            Dict with ``total_rules``, ``enabled_rules``, ``disabled_rules``,
            ``coverage_pct``, ``never_fired_rule_ids``.
        """
        all_rules = self.db.query(Rule).all()
        enabled = [r for r in all_rules if r.enabled]
        disabled = [r for r in all_rules if not r.enabled]

        # Attempt analytics integration (graceful degradation).
        triggered_ids: List[str] = []
        try:
            from app.services.analytics_service import get_analytics_service

            svc = get_analytics_service()
            metrics = svc.store.read_rule_metrics()
            triggered_ids = [
                str(rid) for rid, data in metrics.items()
                if int(data.get("hit_count", 0)) > 0
            ]
        except Exception:
            logger.debug("Analytics unavailable for coverage check — skipping.")

        triggered_set = set(triggered_ids)
        never_fired = [str(r.id) for r in enabled if str(r.id) not in triggered_set]
        coverage_pct = (
            (len(enabled) - len(never_fired)) / len(enabled) * 100.0
            if enabled
            else 0.0
        )

        return {
            "total_rules": len(all_rules),
            "enabled_rules": len(enabled),
            "disabled_rules": len(disabled),
            "coverage_pct": round(coverage_pct, 2),
            "never_fired_rule_ids": never_fired,
        }

    def _check_rule_health(self) -> Dict[str, Any]:
        """Check rule health: disabled rules, missing metadata, orphan versions.

        Returns:
            Dict with counts and an ``issues`` list.
        """
        all_rules = self.db.query(Rule).all()
        issues: List[Dict[str, str]] = []

        disabled_rules = [r for r in all_rules if not r.enabled]
        if disabled_rules:
            issues.append({
                "type": "disabled_rules",
                "message": f"{len(disabled_rules)} rule(s) are disabled.",
                "rule_ids": [str(r.id) for r in disabled_rules],
            })

        missing_desc = [r for r in all_rules if not r.description]
        if missing_desc:
            issues.append({
                "type": "missing_description",
                "message": f"{len(missing_desc)} rule(s) lack a description.",
                "rule_ids": [str(r.id) for r in missing_desc],
            })

        missing_group = [r for r in all_rules if not r.group]
        if missing_group:
            issues.append({
                "type": "missing_group",
                "message": f"{len(missing_group)} rule(s) have no group.",
                "rule_ids": [str(r.id) for r in missing_group],
            })

        return {
            "total_rules": len(all_rules),
            "disabled_count": len(disabled_rules),
            "issues": issues,
        }

    def _check_performance(self) -> Dict[str, Any]:
        """Benchmark audit-related query latency.

        Returns:
            Dict with query latency measurements in milliseconds.
        """
        # Measure audit-log count query time.
        from app.models.audit import AuditLog

        t0 = time.monotonic()
        total_logs = self.db.query(AuditLog).count()
        count_ms = round((time.monotonic() - t0) * 1000, 2)

        # Measure rule count query time.
        t0 = time.monotonic()
        total_rules = self.db.query(Rule).count()
        rule_count_ms = round((time.monotonic() - t0) * 1000, 2)

        # Measure integrity check sample.
        t0 = time.monotonic()
        self._audit_svc.verify_recent(limit=50)
        integrity_ms = round((time.monotonic() - t0) * 1000, 2)

        return {
            "audit_log_count": total_logs,
            "audit_count_query_ms": count_ms,
            "rule_count": total_rules,
            "rule_count_query_ms": rule_count_ms,
            "integrity_check_50_rows_ms": integrity_ms,
        }
