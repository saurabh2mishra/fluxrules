"""
Reusable rule and fact generators for performance testing.

Provides industry-grade rule complexity levels and real-world fact patterns
for performance benchmarking and validation.
"""

import random
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fluxrules import Rule


class ComplexityLevel(Enum):
    """Rule complexity levels."""

    SIMPLE = 1  # Single condition (for baseline)
    MODERATE = 5  # 5-7 conditions (fraud detection baseline)
    ADVANCED = 10  # 10-15 conditions (healthcare, risk scoring)
    ENTERPRISE = 20  # 20-30 conditions (comprehensive risk, cybersecurity)
    EXTREME = 50  # 50+ conditions (extreme edge case, stress testing)


# Rule Generators


def and_rule(
    rid: int,
    n_conditions: int = 5,
    field_space: int = 100,
    rng: random.Random | None = None,
    operators: list[str] | None = None,
) -> Rule:
    """
    Generate a rule with N AND-ed conditions.

    This is the PRIMARY generator for industry-realistic rules. Each condition
    is on a DISTINCT field to avoid redundancy (e.g., avoid `x > 100 AND x > 200`).

    Args:
        rid: Rule ID
        n_conditions: Number of AND-ed conditions (default 5)
        field_space: Total distinct fields available (default 100)
        rng: Random generator (default: random.Random())
        operators: List of allowed operators (default: ">", ">=", "<", "<=", "==", "!=")

    Returns:
        Rule with AND-ed conditions on distinct fields

    Examples:
        >>> and_rule(1, n_conditions=8)  # Fraud detection
        >>> and_rule(2, n_conditions=20) # Risk scoring
        >>> and_rule(3, n_conditions=30) # Comprehensive assessment
    """
    if rng is None:
        rng = random.Random()
    if operators is None:
        operators = [">", ">=", "<", "<=", "==", "!="]

    # Select n_conditions distinct fields
    available_fields = min(n_conditions, field_space)
    fields = rng.sample(range(available_fields), available_fields)[:n_conditions]

    conditions = [
        {
            "type": "condition",
            "field": f"field_{f}",
            "op": rng.choice(operators),
            "value": rng.randint(0, 1000),
        }
        for f in fields
    ]

    return Rule(
        id=rid,
        name=f"rule_{rid}_and{n_conditions}",
        condition_dsl={"type": "and", "conditions": conditions},
        priority=rid % 10,
        domain=f"d{rid % 5}",
        tags=frozenset([f"tag_{rid % 3}"]),
        persist=False,
    )


def and_heavy_rules(
    n_rules: int,
    n_conditions: int = 20,
    field_space: int = 100,
    rng: random.Random | None = None,
) -> list[Rule]:
    """
    Generate N rules with M AND-ed conditions each (industry-realistic).

    Args:
        n_rules: Number of rules to generate
        n_conditions: Conditions per rule
        field_space: Total distinct fields
        rng: Random generator

    Returns:
        List of N rules with M AND-ed conditions
    """
    if rng is None:
        rng = random.Random()
    return [and_rule(i, n_conditions, field_space, rng) for i in range(n_rules)]


def mixed_complexity_rules(
    n_rules: int,
    rng: random.Random | None = None,
) -> list[Rule]:
    """
    Generate N rules with MIXED complexity (realistic rule set).

    Distribution:
    - 30% simple (1-3 conditions) - basic filters
    - 40% moderate (5-10 conditions) - fraud, basic risk
    - 20% advanced (10-15 conditions) - healthcare, detailed risk
    - 10% enterprise (20-25 conditions) - comprehensive assessment

    Args:
        n_rules: Number of rules
        rng: Random generator

    Returns:
        List of rules with mixed complexity
    """
    if rng is None:
        rng = random.Random()

    rules = []
    thresholds = [0.3, 0.7, 0.9]  # 30%, 40%, 20%, 10%

    for rid in range(n_rules):
        roll = rng.random()
        if roll < thresholds[0]:
            n_cond = rng.randint(1, 3)
        elif roll < thresholds[1]:
            n_cond = rng.randint(5, 10)
        elif roll < thresholds[2]:
            n_cond = rng.randint(10, 15)
        else:
            n_cond = rng.randint(20, 25)

        rules.append(and_rule(rid, n_cond, rng=rng))

    return rules


def nested_bool_rules(
    n_rules: int,
    max_depth: int = 2,
    rng: random.Random | None = None,
) -> list[Rule]:
    """
    Generate N rules with nested AND/OR/NOT boolean structures.

    Args:
        n_rules: Number of rules
        max_depth: Maximum nesting depth
        rng: Random generator

    Returns:
        List of rules with nested boolean expressions
    """
    if rng is None:
        rng = random.Random()

    def _build_condition(depth: int) -> dict:
        if depth <= 0 or rng.random() < 0.5:
            field = f"field_{rng.randint(0, 100)}"
            return {
                "type": "condition",
                "field": field,
                "op": rng.choice([">", ">=", "<", "<=", "==", "!="]),
                "value": rng.randint(0, 1000),
            }

        ctype = rng.choice(["and", "or"])
        n_children = rng.randint(2, 3)
        conditions = [_build_condition(depth - 1) for _ in range(n_children)]
        return {"type": ctype, "conditions": conditions}

    return [
        Rule(
            id=rid,
            name=f"rule_{rid}_nested",
            condition_dsl=_build_condition(max_depth),
            priority=rid % 10,
            domain=f"d{rid % 5}",
            tags=frozenset(),
            persist=False,
        )
        for rid in range(n_rules)
    ]


# Fact Generators (Real-World Scenarios)


@dataclass
class FactGeneratorConfig:
    """Configuration for fact generation."""

    n_fields: int = 50
    fact_density: float = 0.8  # Fraction of fields to include


# --- Fraud Detection Scenario ---


def fraud_fact(rng: random.Random | None = None) -> dict[str, Any]:
    """
    Generate a fact for fraud detection scenario.

    Fields:
    - amount: transaction amount ($0-$100k)
    - merchant_category: MCC code
    - user_age: customer age (18-85)
    - account_velocity: transactions/hour (0-100)
    - country: merchant country code
    - device_id: device used (hashed)
    - time_of_day: hour (0-23)
    - days_since_signup: account age (0-3650)
    - failed_attempts_24h: failed authentications (0-50)
    - unusual_location: distance from home (0-5000 miles)
    - card_velocity_24h: card usage velocity (0-100)
    - previous_fraud_flag: binary (0-1)
    """
    if rng is None:
        rng = random.Random()

    return {
        "amount": rng.randint(1, 100000),
        "merchant_category": rng.randint(1000, 9999),
        "user_age": rng.randint(18, 85),
        "account_velocity": rng.randint(0, 100),
        "country": rng.randint(1, 250),
        "device_id": rng.randint(1, 1000000),
        "time_of_day": rng.randint(0, 23),
        "days_since_signup": rng.randint(0, 3650),
        "failed_attempts_24h": rng.randint(0, 50),
        "unusual_location": rng.randint(0, 5000),
        "card_velocity_24h": rng.randint(0, 100),
        "previous_fraud_flag": rng.randint(0, 1),
    }


def fraud_facts(n: int, rng: random.Random | None = None) -> list[dict]:
    """Generate N fraud detection facts."""
    if rng is None:
        rng = random.Random()
    return [fraud_fact(rng) for _ in range(n)]


# --- Healthcare Risk Scenario ---


def health_risk_fact(rng: random.Random | None = None) -> dict[str, Any]:
    """
    Generate a fact for healthcare readmission risk scenario.

    Fields:
    - age: patient age (0-100)
    - bmi: body mass index (15-40)
    - systolic_bp: systolic blood pressure (80-200)
    - diastolic_bp: diastolic blood pressure (40-120)
    - glucose: fasting glucose (60-400)
    - hemoglobin_a1c: HbA1c percent (4.5-14)
    - egfr: estimated glomerular filtration rate (5-120)
    - creatinine: serum creatinine (0.6-5.0)
    - comorbidity_count: number of comorbidities (0-15)
    - medication_count: number of medications (0-30)
    - days_since_discharge: days (0-365)
    - depression_flag: binary (0-1)
    - smoking_status: 0=never, 1=former, 2=current
    - social_support: score 1-10
    """
    if rng is None:
        rng = random.Random()

    return {
        "age": rng.randint(0, 100),
        "bmi": round(rng.uniform(15, 40), 1),
        "systolic_bp": rng.randint(80, 200),
        "diastolic_bp": rng.randint(40, 120),
        "glucose": rng.randint(60, 400),
        "hemoglobin_a1c": round(rng.uniform(4.5, 14), 1),
        "egfr": rng.randint(5, 120),
        "creatinine": round(rng.uniform(0.6, 5.0), 1),
        "comorbidity_count": rng.randint(0, 15),
        "medication_count": rng.randint(0, 30),
        "days_since_discharge": rng.randint(0, 365),
        "depression_flag": rng.randint(0, 1),
        "smoking_status": rng.randint(0, 2),
        "social_support": rng.randint(1, 10),
    }


def health_risk_facts(n: int, rng: random.Random | None = None) -> list[dict]:
    """Generate N healthcare risk facts."""
    if rng is None:
        rng = random.Random()
    return [health_risk_fact(rng) for _ in range(n)]


# --- Cybersecurity Threat Detection Scenario ---


def cybersecurity_fact(rng: random.Random | None = None) -> dict[str, Any]:
    """
    Generate a fact for cybersecurity threat detection scenario.

    Fields:
    - failed_logins_5m: failed login attempts in 5 min (0-50)
    - unique_ips_24h: unique IPs accessed from (0-100)
    - outbound_gb_hour: outbound data GB/hour (0-100)
    - privilege_escalation: binary (0-1)
    - unusual_ports: count of unusual ports accessed (0-20)
    - vpn_connected: binary (0-1)
    - after_hours: binary (0-1)
    - lateral_movement: binary (0-1)
    - sensitive_data_access: binary (0-1)
    - api_rate_exceeded: binary (0-1)
    - security_group_modified: binary (0-1)
    - user_risk_score: 0-100
    - command_execution_count: count (0-1000)
    - registry_modification: binary (0-1)
    """
    if rng is None:
        rng = random.Random()

    return {
        "failed_logins_5m": rng.randint(0, 50),
        "unique_ips_24h": rng.randint(0, 100),
        "outbound_gb_hour": rng.randint(0, 100),
        "privilege_escalation": rng.randint(0, 1),
        "unusual_ports": rng.randint(0, 20),
        "vpn_connected": rng.randint(0, 1),
        "after_hours": rng.randint(0, 1),
        "lateral_movement": rng.randint(0, 1),
        "sensitive_data_access": rng.randint(0, 1),
        "api_rate_exceeded": rng.randint(0, 1),
        "security_group_modified": rng.randint(0, 1),
        "user_risk_score": rng.randint(0, 100),
        "command_execution_count": rng.randint(0, 1000),
        "registry_modification": rng.randint(0, 1),
    }


def cybersecurity_facts(n: int, rng: random.Random | None = None) -> list[dict]:
    """Generate N cybersecurity threat detection facts."""
    if rng is None:
        rng = random.Random()
    return [cybersecurity_fact(rng) for _ in range(n)]


# --- Generic Multi-Field Scenario ---


def sparse_fact(
    n_fields: int = 100,
    density: float = 0.4,
    rng: random.Random | None = None,
) -> dict[str, int]:
    """
    Generate a sparse fact (not all fields present).

    Args:
        n_fields: Total possible fields
        density: Fraction of fields to include (e.g., 0.4 = 40%)
        rng: Random generator

    Returns:
        Dictionary with ~density% of fields
    """
    if rng is None:
        rng = random.Random()

    return {f"field_{i}": rng.randint(0, 1000) for i in range(n_fields) if rng.random() < density}


def sparse_facts(
    n: int,
    n_fields: int = 100,
    density: float = 0.4,
    rng: random.Random | None = None,
) -> list[dict]:
    """Generate N sparse facts."""
    if rng is None:
        rng = random.Random()
    return [sparse_fact(n_fields, density, rng) for _ in range(n)]


# --- Hot Field Distribution ---


def hot_field_fact(
    hot_fields: list[str],
    cold_fields: int = 50,
    cold_density: float = 0.3,
    rng: random.Random | None = None,
) -> dict[str, int]:
    """
    Generate a fact with HOT fields (always present) + COLD fields (sparse).

    This is REALISTIC: some fields appear in every fact (amount, timestamp),
    while others are optional (custom_field_1, custom_field_2, etc).

    Args:
        hot_fields: Fields that always appear
        cold_fields: Number of cold/sparse fields
        cold_density: Fraction of cold fields to include per fact
        rng: Random generator

    Returns:
        Dict with hot fields + sparse cold fields
    """
    if rng is None:
        rng = random.Random()

    fact = {}

    # Always include hot fields
    for field in hot_fields:
        fact[field] = rng.randint(0, 1000)

    # Sparsely include cold fields
    for i in range(cold_fields):
        if rng.random() < cold_density:
            fact[f"cold_field_{i}"] = rng.randint(0, 1000)

    return fact


def hot_field_facts(
    n: int,
    hot_fields: list[str],
    cold_fields: int = 50,
    cold_density: float = 0.3,
    rng: random.Random | None = None,
) -> list[dict]:
    """Generate N facts with hot/cold field distribution."""
    if rng is None:
        rng = random.Random()
    return [hot_field_fact(hot_fields, cold_fields, cold_density, rng) for _ in range(n)]
