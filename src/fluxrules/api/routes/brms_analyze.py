"""BRMS Analysis endpoint - bulk and individual rule analysis."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from fluxrules.api.database import get_db
from fluxrules.api.deps import get_current_user
from fluxrules.api.models.user import User
from fluxrules.api.services.brms_service import BRMSService
from fluxrules.api.services.rule_service import RuleService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brms", tags=["brms"])

# Shared BRMS service instance (stateless - safe as a module-level singleton).
_brms_service = BRMSService()

# NOTE: RuleService requires a per-request `Session`, so it must NOT be
# instantiated at import time. Doing so raised a TypeError that silently
# disabled this entire router in every deployment. Construct it inside each
# handler from the request-scoped `db` dependency instead.

# Request/Response Models


class RuleAnalysisRequest(BaseModel):
    """Request to analyze individual rules or a rule set."""

    rule_ids: list[str] | None = Field(
        None,
        description="Specific rule IDs to analyze. If None, analyzes all rules in the group/domain.",
    )
    group: str | None = Field(
        None, description="Filter by rule group. If None, analyzes all groups."
    )
    include_coverage: bool = Field(True, description="Include coverage analysis in the report.")
    include_conflicts: bool = Field(True, description="Include conflict detection in the report.")
    include_redundancy: bool = Field(
        True, description="Include redundancy detection in the report."
    )
    include_dead_rules: bool = Field(True, description="Include dead rule detection in the report.")
    include_gaps: bool = Field(True, description="Include gap detection in the report.")
    include_duplicates: bool = Field(True, description="Include duplicate detection in the report.")
    include_priority_issues: bool = Field(
        True, description="Include priority collision detection in the report."
    )


class ConflictDetail(BaseModel):
    """Details about a detected conflict."""

    type: str
    rule_id: str | None = None
    description: str
    related_rule_ids: list[str] | None = None
    severity: str = Field(default="warning")


class RedundancyDetail(BaseModel):
    """Details about detected redundancy."""

    type: str
    rule_id: str
    description: str
    related_rule_ids: list[str] | None = None


class DeadRuleDetail(BaseModel):
    """Details about a dead rule."""

    rule_id: str
    name: str | None = None
    reason: str
    severity: str = Field(default="error")


class GapDetail(BaseModel):
    """Details about detected gaps in rule coverage."""

    type: str
    description: str
    affected_conditions: list[str] | None = None
    recommendation: str


class DuplicateDetail(BaseModel):
    """Details about duplicate rules."""

    rule_id_1: str
    rule_id_2: str
    similarity_score: float
    duplicate_type: str


class PriorityIssueDetail(BaseModel):
    """Details about priority-related issues."""

    rule_id: str
    issue: str
    conflicting_rule_ids: list[str]
    description: str


class CoverageAnalysisDetail(BaseModel):
    """Coverage analysis for a rule set."""

    total_rules: int
    triggered_rules: int
    coverage_percentage: float
    untriggered_rules: list[str]


class BRMSAnalysisReport(BaseModel):
    """Comprehensive BRMS analysis report."""

    summary: dict[str, Any] = Field(
        default_factory=dict, description="Summary statistics of the analysis."
    )
    conflicts: list[ConflictDetail] = Field(default_factory=list, description="Detected conflicts.")
    redundancies: list[RedundancyDetail] = Field(
        default_factory=list, description="Detected redundancies."
    )
    dead_rules: list[DeadRuleDetail] = Field(
        default_factory=list, description="Detected dead rules."
    )
    gaps: list[GapDetail] = Field(default_factory=list, description="Detected coverage gaps.")
    duplicates: list[DuplicateDetail] = Field(
        default_factory=list, description="Detected duplicate rules."
    )
    priority_issues: list[PriorityIssueDetail] = Field(
        default_factory=list, description="Detected priority issues."
    )
    coverage: CoverageAnalysisDetail | None = Field(
        default=None, description="Coverage analysis results."
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable recommendations."
    )


# Endpoints


@router.post(
    "/analyze",
    response_model=BRMSAnalysisReport,
    summary="Analyze rules for BRMS issues",
    description="Comprehensive analysis of rules for conflicts, redundancy, dead rules, gaps, and coverage issues. Supports both bulk analysis and individual rule analysis.",
)
def analyze_rules(
    request: RuleAnalysisRequest = Body(
        ...,
        examples=[
            {
                "summary": "Analyze rules with all report sections enabled",
                "value": {
                    "rule_ids": None,
                    "group": None,
                    "include_coverage": True,
                    "include_conflicts": True,
                    "include_redundancy": True,
                    "include_dead_rules": True,
                    "include_gaps": True,
                    "include_duplicates": True,
                    "include_priority_issues": True,
                },
            }
        ],
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BRMSAnalysisReport:
    """
    Analyze rules for BRMS (Business Rule Management System) issues.

    This endpoint performs comprehensive analysis of rules to identify:
    - **Conflicts**: Rules with overlapping conditions
    - **Redundancy**: Rules that are logically equivalent or subsumed by others
    - **Dead Rules**: Rules that can never fire due to their conditions
    - **Coverage Gaps**: Missing conditions that should be handled
    - **Duplicates**: Exact or near-exact duplicate rules
    - **Priority Issues**: Priority collision and reachability problems

    **Query Modes:**
    - **Bulk Analysis**: Omit `rule_ids` to analyze all rules (or filtered by `group`)
    - **Targeted Analysis**: Specify `rule_ids` to analyze specific rules

    **Example Usage:**

    ```json
    {
      "rule_ids": ["rule_1", "rule_2"],
      "include_conflicts": true,
      "include_dead_rules": true
    }
    ```

    **Response:**
    Returns a comprehensive report with:
    - Summary statistics
    - Detailed findings for each category
    - Actionable recommendations
    """
    try:
        # Step 1: Fetch rules from database
        all_rules = RuleService(db).list_rules(limit=10_000)
        if not all_rules:
            return BRMSAnalysisReport(
                summary={
                    "total_rules_analyzed": 0,
                    "issues_found": 0,
                    "analysis_status": "no_rules",
                }
            )

        # Filter by group if provided
        if request.group:
            all_rules = [r for r in all_rules if r.group == request.group]

        # Filter by specific rule_ids if provided
        if request.rule_ids:
            rule_ids_set = set(request.rule_ids)
            rules_to_analyze = [r for r in all_rules if r.id in rule_ids_set]
            # For related analysis, still use all rules for context
        else:
            rules_to_analyze = all_rules

        if not rules_to_analyze:
            return BRMSAnalysisReport(
                summary={
                    "total_rules_analyzed": 0,
                    "issues_found": 0,
                    "analysis_status": "no_matching_rules",
                }
            )

        # Convert rules to dict format for analysis
        rules_dicts: list[dict[str, Any]] = [
            {
                "id": r.id,
                "name": r.name,
                "condition_dsl": r.condition_dsl,
                "priority": r.priority,
                "enabled": r.enabled,
                "action": r.action,
                "group": r.group,
            }
            for r in all_rules
        ]

        # Step 2: Run comprehensive validation
        validation_results = _brms_service.validate(rules_dicts)

        # Step 3: Build analysis report
        report = _build_analysis_report(validation_results, rules_to_analyze, request)

        return report

    except Exception as e:
        logger.error(f"Error analyzing rules: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e!s}") from e


@router.get(
    "/analyze/summary",
    summary="Quick analysis summary",
    description="Get a quick summary of rule analysis without detailed findings.",
)
def analyze_summary(
    group: str | None = Query(None, description="Filter by group"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Get a quick summary of rule analysis issues without detailed findings.

    **Response includes:**
    - Total rules analyzed
    - Count of issues by type
    - Severity breakdown
    - Quick health score (0-100)

    **Example Response:**
    ```json
    {
      "total_rules": 42,
      "total_issues": 5,
      "conflicts_count": 2,
      "dead_rules_count": 1,
      "redundancy_count": 2,
      "health_score": 88,
      "issues_by_severity": {
        "error": 1,
        "warning": 3,
        "info": 1
      }
    }
    ```
    """
    try:
        all_rules = RuleService(db).list_rules(limit=10_000)

        if group:
            all_rules = [r for r in all_rules if r.group == group]

        if not all_rules:
            return {
                "total_rules": 0,
                "total_issues": 0,
                "health_score": 100,
                "status": "no_rules",
            }

        # Convert to dict format
        rules_dicts = [
            {
                "id": r.id,
                "name": r.name,
                "condition_dsl": r.condition_dsl,
                "priority": r.priority,
                "enabled": r.enabled,
                "action": r.action,
                "group": r.group,
            }
            for r in all_rules
        ]

        validation = _brms_service.validate(rules_dicts)

        # Calculate summary
        summary = {
            "total_rules": len(all_rules),
            "conflicts_count": len(validation.get("conflicts", [])),
            "dead_rules_count": len(validation.get("dead_rules", [])),
            "redundancy_count": len(validation.get("redundancies", [])),
            "gaps_count": len(validation.get("gaps", [])),
            "duplicates_count": len(validation.get("duplicates", [])),
            "priority_issues_count": len(validation.get("priority_collisions", [])),
        }

        total_issues = sum(
            [
                summary["conflicts_count"],
                summary["dead_rules_count"],
                summary["redundancy_count"],
                summary["gaps_count"],
                summary["duplicates_count"],
                summary["priority_issues_count"],
            ]
        )

        summary["total_issues"] = total_issues
        summary["health_score"] = max(0, 100 - (total_issues * 5))

        return summary

    except Exception as e:
        logger.error(f"Error generating summary: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {e!s}") from e


# Helper Functions


def _build_analysis_report(
    validation_results: dict[str, Any],
    analyzed_rules: list[Any],
    request: RuleAnalysisRequest,
) -> BRMSAnalysisReport:
    """Build comprehensive analysis report from validation results."""

    report = BRMSAnalysisReport()

    # Add conflicts
    if request.include_conflicts:
        conflicts = validation_results.get("conflicts", [])
        for conflict in conflicts:
            conflict_detail = ConflictDetail(
                type=conflict.get("type", "conflict"),
                rule_id=conflict.get("rule_id"),
                description=conflict.get("description", "Conflicting rules detected"),
                severity="warning",
            )
            report.conflicts.append(conflict_detail)

    # Add redundancies
    if request.include_redundancy:
        redundancies = validation_results.get("redundancies", [])
        for redundancy in redundancies:
            red_detail = RedundancyDetail(
                type="redundant_rule",
                rule_id=redundancy.get("id", "unknown"),
                description=redundancy.get("description", "Rule is redundant"),
            )
            report.redundancies.append(red_detail)

    # Add dead rules
    if request.include_dead_rules:
        dead_rules = validation_results.get("dead_rules", [])
        for dead in dead_rules:
            dead_detail = DeadRuleDetail(
                rule_id=dead.get("id", dead.get("rule_id", "unknown")),
                name=dead.get("name"),
                reason=dead.get("reason", "Rule is dead"),
                severity="error",
            )
            report.dead_rules.append(dead_detail)

    # Add gaps
    if request.include_gaps:
        gaps = validation_results.get("gaps", [])
        for gap in gaps:
            gap_detail = GapDetail(
                type="coverage_gap",
                description=gap.get("description", "Coverage gap detected"),
                recommendation=gap.get("recommendation", "Review rule conditions"),
            )
            report.gaps.append(gap_detail)

    # Add duplicates
    if request.include_duplicates:
        duplicates = validation_results.get("duplicates", [])
        for dup in duplicates:
            dup_detail = DuplicateDetail(
                rule_id_1=dup.get("rule_id_1", "unknown"),
                rule_id_2=dup.get("rule_id_2", "unknown"),
                similarity_score=dup.get("similarity", 0.95),
                duplicate_type=dup.get("type", "exact"),
            )
            report.duplicates.append(dup_detail)

    # Add priority issues
    if request.include_priority_issues:
        collisions = validation_results.get("priority_collisions", [])
        for collision in collisions:
            priority_issue = PriorityIssueDetail(
                rule_id=collision.get("rule_id", "unknown"),
                issue=collision.get("issue", "Priority issue"),
                conflicting_rule_ids=collision.get("conflicting_rules", []),
                description=collision.get("description", "Priority conflict"),
            )
            report.priority_issues.append(priority_issue)

    # Calculate summary
    total_issues = (
        len(report.conflicts)
        + len(report.redundancies)
        + len(report.dead_rules)
        + len(report.gaps)
        + len(report.duplicates)
        + len(report.priority_issues)
    )

    report.summary = {
        "total_rules_analyzed": len(analyzed_rules),
        "total_issues_found": total_issues,
        "issue_breakdown": {
            "conflicts": len(report.conflicts),
            "redundancies": len(report.redundancies),
            "dead_rules": len(report.dead_rules),
            "gaps": len(report.gaps),
            "duplicates": len(report.duplicates),
            "priority_issues": len(report.priority_issues),
        },
        "health_score": max(0, 100 - (total_issues * 3)),
        "analysis_status": "completed",
    }

    # Add recommendations
    report.recommendations = _generate_recommendations(validation_results)

    return report


def _generate_recommendations(validation_results: dict[str, Any]) -> list[str]:
    """Generate actionable recommendations based on analysis results."""
    recommendations = []

    dead_rules = validation_results.get("dead_rules", [])
    if dead_rules:
        recommendations.append(
            f"Remove or fix {len(dead_rules)} dead rule(s) that cannot be triggered"
        )

    conflicts = validation_results.get("conflicts", [])
    if conflicts:
        recommendations.append(
            f"Review {len(conflicts)} conflicting rule(s) and adjust priorities or conditions"
        )

    redundancies = validation_results.get("redundancies", [])
    if redundancies:
        recommendations.append(
            f"Consolidate {len(redundancies)} redundant rule(s) to reduce complexity"
        )

    gaps = validation_results.get("gaps", [])
    if gaps:
        recommendations.append(
            f"Address {len(gaps)} coverage gap(s) to ensure complete rule coverage"
        )

    duplicates = validation_results.get("duplicates", [])
    if duplicates:
        recommendations.append(
            f"Remove {len(duplicates)} duplicate rule(s) to eliminate redundancy"
        )

    collisions = validation_results.get("priority_collisions", [])
    if collisions:
        recommendations.append(
            f"Fix {len(collisions)} priority collision(s) to ensure predictable rule execution order"
        )

    if not recommendations:
        recommendations.append("No critical issues found. Rule set is healthy!")

    return recommendations
