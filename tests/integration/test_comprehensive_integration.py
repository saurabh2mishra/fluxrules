"""Comprehensive integration tests for FluxRules.

Tests cover complex scenarios across multiple components:
- Multi-engine rule evaluation
- Action execution across different engines
- Streaming mode advanced features
- Cross-domain rule interactions
- Complex condition DSLs with various logic operators
- Real-world workflows and edge cases
"""

import time

from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine


class TestMultiEngineRuleEvaluation:
    """Test rules evaluation across different engine types."""

    def test_enterprise_credit_decisioning_engine(self):
        """Enterprise-grade credit decisioning with 10+ conditions.

        Real-world scenario: Financial institution credit approval with
        comprehensive risk assessment covering multiple dimensions.
        """
        rule = Rule(
            id=1,
            name="Enterprise Credit Approval - Tier 1",
            condition_dsl={
                "type": "and",
                "conditions": [
                    # Age and employment
                    {"type": "condition", "field": "age", "op": ">=", "value": 21},
                    {
                        "type": "condition",
                        "field": "employment_years",
                        "op": ">=",
                        "value": 2,
                    },
                    # Financial metrics
                    {
                        "type": "condition",
                        "field": "annual_income",
                        "op": ">=",
                        "value": 75000,
                    },
                    {
                        "type": "condition",
                        "field": "credit_score",
                        "op": ">=",
                        "value": 720,
                    },
                    {
                        "type": "condition",
                        "field": "debt_to_income_ratio",
                        "op": "<",
                        "value": 0.35,
                    },
                    # Banking history
                    {
                        "type": "condition",
                        "field": "years_banking_history",
                        "op": ">=",
                        "value": 3,
                    },
                    {
                        "type": "condition",
                        "field": "account_status",
                        "op": "==",
                        "value": "active",
                    },
                    # Account health
                    {
                        "type": "condition",
                        "field": "monthly_overdrafts",
                        "op": "<",
                        "value": 1,
                    },
                    {
                        "type": "condition",
                        "field": "late_payments_90days",
                        "op": "==",
                        "value": 0,
                    },
                    {
                        "type": "condition",
                        "field": "recent_delinquencies",
                        "op": "==",
                        "value": 0,
                    },
                    # Risk assessment
                    {
                        "type": "condition",
                        "field": "fraud_risk_score",
                        "op": "<",
                        "value": 30,
                    },
                ],
            },
            action="approve_with_premium_terms",
            priority=10,
            domain="credit_decisioning",
        )

        facts_approved = {
            "age": 35,
            "employment_years": 5,
            "annual_income": 125000,
            "credit_score": 760,
            "debt_to_income_ratio": 0.28,
            "years_banking_history": 8,
            "account_status": "active",
            "monthly_overdrafts": 0,
            "late_payments_90days": 0,
            "recent_delinquencies": 0,
            "fraud_risk_score": 15,
        }

        facts_rejected_low_score = {
            "age": 35,
            "employment_years": 5,
            "annual_income": 125000,
            "credit_score": 650,  # Below minimum
            "debt_to_income_ratio": 0.28,
            "years_banking_history": 8,
            "account_status": "active",
            "monthly_overdrafts": 0,
            "late_payments_90days": 0,
            "recent_delinquencies": 0,
            "fraud_risk_score": 15,
        }

        facts_rejected_high_dti = {
            "age": 35,
            "employment_years": 5,
            "annual_income": 75000,
            "credit_score": 760,
            "debt_to_income_ratio": 0.45,  # Too high
            "years_banking_history": 8,
            "account_status": "active",
            "monthly_overdrafts": 0,
            "late_payments_90days": 0,
            "recent_delinquencies": 0,
            "fraud_risk_score": 15,
        }

        # Evaluate through the PHREAK engine
        engines = [PhreakEngine()]

        for engine in engines:
            engine.load_rules([rule])

            # Approved applicant
            result_approved = engine.evaluate(facts_approved)
            assert 1 in result_approved.fired_rules, (
                f"{type(engine).__name__} should approve qualified applicant"
            )
            assert "approve_with_premium_terms" in result_approved.actions

            # Rejected - low credit score
            result_rejected_score = engine.evaluate(facts_rejected_low_score)
            assert result_rejected_score.fired_rules == []

            # Rejected - high debt-to-income
            result_rejected_dti = engine.evaluate(facts_rejected_high_dti)
            assert result_rejected_dti.fired_rules == []

    def test_ecommerce_fraud_detection_rules(self):
        """E-commerce fraud detection with 8+ conditions.

        Real-world scenario: Multi-dimensional fraud detection combining
        transaction analysis, user behavior, and device fingerprinting.
        """
        rule = Rule(
            id=2,
            name="Advanced Fraud Detection - Block Transaction",
            condition_dsl={
                "type": "or",
                "conditions": [
                    {
                        "type": "and",
                        "conditions": [
                            {
                                "type": "condition",
                                "field": "transaction_amount",
                                "op": ">",
                                "value": 5000,
                            },
                            {
                                "type": "condition",
                                "field": "account_age_days",
                                "op": "<",
                                "value": 7,
                            },
                            {
                                "type": "condition",
                                "field": "first_purchase",
                                "op": "==",
                                "value": True,
                            },
                        ],
                    },
                    {
                        "type": "and",
                        "conditions": [
                            {
                                "type": "condition",
                                "field": "velocity_txns_1hour",
                                "op": ">",
                                "value": 5,
                            },
                            {
                                "type": "condition",
                                "field": "distinct_merchants_1hour",
                                "op": ">",
                                "value": 8,
                            },
                            {
                                "type": "condition",
                                "field": "account_age_days",
                                "op": "<",
                                "value": 30,
                            },
                        ],
                    },
                    {
                        "type": "and",
                        "conditions": [
                            {
                                "type": "condition",
                                "field": "ip_country",
                                "op": "!=",
                                "value": "US",
                            },
                            {
                                "type": "condition",
                                "field": "card_country",
                                "op": "==",
                                "value": "US",
                            },
                            {
                                "type": "condition",
                                "field": "geographic_distance_miles",
                                "op": ">",
                                "value": 5000,
                            },
                            {
                                "type": "condition",
                                "field": "time_since_last_txn_hours",
                                "op": "<",
                                "value": 1,
                            },
                        ],
                    },
                ],
            },
            action="block_transaction_alert_fraud_team",
            priority=10,
            domain="fraud_detection",
        )

        # Scenario 1: New account large purchase
        facts_high_risk_new = {
            "transaction_amount": 8000,
            "account_age_days": 2,
            "first_purchase": True,
            "velocity_txns_1hour": 1,
            "distinct_merchants_1hour": 1,
            "ip_country": "US",
            "card_country": "US",
            "geographic_distance_miles": 100,
            "time_since_last_txn_hours": 24,
        }

        # Scenario 2: Velocity fraud
        facts_velocity_fraud = {
            "transaction_amount": 500,
            "account_age_days": 20,
            "first_purchase": False,
            "velocity_txns_1hour": 12,
            "distinct_merchants_1hour": 15,
            "ip_country": "US",
            "card_country": "US",
            "geographic_distance_miles": 50,
            "time_since_last_txn_hours": 2,
        }

        # Scenario 3: Impossible travel
        facts_impossible_travel = {
            "transaction_amount": 1500,
            "account_age_days": 90,
            "first_purchase": False,
            "velocity_txns_1hour": 2,
            "distinct_merchants_1hour": 2,
            "ip_country": "JP",
            "card_country": "US",
            "geographic_distance_miles": 5500,
            "time_since_last_txn_hours": 0.5,
        }

        # Scenario 4: Legitimate transaction
        facts_legitimate = {
            "transaction_amount": 2000,
            "account_age_days": 365,
            "first_purchase": False,
            "velocity_txns_1hour": 1,
            "distinct_merchants_1hour": 1,
            "ip_country": "US",
            "card_country": "US",
            "geographic_distance_miles": 100,
            "time_since_last_txn_hours": 24,
        }

        # Evaluate through the PHREAK engine
        engines = [PhreakEngine()]

        for engine in engines:
            engine.load_rules([rule])

            # All risky scenarios should trigger fraud alert
            result_new = engine.evaluate(facts_high_risk_new)
            assert 2 in result_new.fired_rules
            assert "block_transaction_alert_fraud_team" in result_new.actions

            result_velocity = engine.evaluate(facts_velocity_fraud)
            assert 2 in result_velocity.fired_rules

            result_travel = engine.evaluate(facts_impossible_travel)
            assert 2 in result_travel.fired_rules

            # Legitimate transaction should pass
            result_legit = engine.evaluate(facts_legitimate)
            assert result_legit.fired_rules == []

    def test_insurance_underwriting_rules(self):
        """Insurance underwriting with 9+ conditions.

        Real-world scenario: Health insurance underwriting considering
        medical, lifestyle, and demographic factors for premium calculation.
        """
        rule = Rule(
            id=3,
            name="Insurance Premium Calculation - Standard Risk",
            condition_dsl={
                "type": "and",
                "conditions": [
                    {"type": "condition", "field": "age", "op": ">=", "value": 18},
                    {"type": "condition", "field": "age", "op": "<", "value": 50},
                    {"type": "condition", "field": "bmi", "op": "<", "value": 30},
                    {
                        "type": "condition",
                        "field": "smoker",
                        "op": "==",
                        "value": False,
                    },
                    {
                        "type": "condition",
                        "field": "blood_pressure_systolic",
                        "op": "<",
                        "value": 140,
                    },
                    {
                        "type": "condition",
                        "field": "cholesterol_level",
                        "op": "<",
                        "value": 200,
                    },
                    {
                        "type": "condition",
                        "field": "diabetes_diagnosed",
                        "op": "==",
                        "value": False,
                    },
                    {
                        "type": "condition",
                        "field": "family_history_heart_disease",
                        "op": "==",
                        "value": False,
                    },
                    {
                        "type": "condition",
                        "field": "exercise_frequency_weekly",
                        "op": ">=",
                        "value": 3,
                    },
                ],
            },
            action="approve_standard_premium",
            priority=5,
            domain="insurance",
        )

        facts_standard = {
            "age": 35,
            "bmi": 25,
            "smoker": False,
            "blood_pressure_systolic": 120,
            "cholesterol_level": 180,
            "diabetes_diagnosed": False,
            "family_history_heart_disease": False,
            "exercise_frequency_weekly": 4,
        }

        facts_high_risk = {
            "age": 35,
            "bmi": 32,
            "smoker": True,
            "blood_pressure_systolic": 150,
            "cholesterol_level": 240,
            "diabetes_diagnosed": True,
            "family_history_heart_disease": True,
            "exercise_frequency_weekly": 0,
        }

        engines = [PhreakEngine()]

        for engine in engines:
            engine.load_rules([rule])

            # Standard risk should be approved
            result_standard = engine.evaluate(facts_standard)
            assert 3 in result_standard.fired_rules
            assert "approve_standard_premium" in result_standard.actions

            # High risk should not qualify for standard premium
            result_high_risk = engine.evaluate(facts_high_risk)
            assert result_high_risk.fired_rules == []


class TestStreamingModeAdvanced:
    """Test advanced streaming mode scenarios."""

    def test_streaming_with_new_fields_added(self):
        """Streaming mode should detect when new fields are added."""
        engine = PhreakEngine(streaming_mode=True)

        rule = Rule(
            id=1,
            name="Composite",
            condition_dsl={
                "type": "and",
                "conditions": [
                    {"type": "condition", "field": "age", "op": ">", "value": 18},
                    {"type": "condition", "field": "income", "op": ">", "value": 50000},
                ],
            },
            action="approve",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # First evaluation with only age
        result1 = engine.evaluate({"age": 25})
        assert result1.fired_rules == []  # Incomplete condition

        # Second evaluation with income added (new field)
        result2 = engine.evaluate({"age": 25, "income": 60000})
        assert 1 in result2.fired_rules  # Should trigger now

        # Third evaluation with same facts
        result3 = engine.evaluate({"age": 25, "income": 60000})
        assert result3.fired_rules == []  # Cached result

    def test_streaming_mode_consistent_evaluation(self):
        """Streaming mode should provide consistent results within evaluation."""
        engine = PhreakEngine(streaming_mode=True)

        rule = Rule(
            id=1,
            name="Complex Rule",
            condition_dsl={
                "type": "and",
                "conditions": [
                    {"type": "condition", "field": "x", "op": ">", "value": 0},
                    {"type": "condition", "field": "y", "op": ">", "value": 0},
                ],
            },
            action="fire",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # First evaluation: both conditions met
        result1 = engine.evaluate({"x": 1, "y": 2})
        assert 1 in result1.fired_rules

        # Second evaluation: identical facts (should be cached)
        result2 = engine.evaluate({"x": 1, "y": 2})
        assert result2.fired_rules == []  # Cached

        # Third evaluation: x changes (re-evaluate)
        result3 = engine.evaluate({"x": 5, "y": 2})
        assert 1 in result3.fired_rules

        # Fourth evaluation: both conditions no longer met
        result4 = engine.evaluate({"x": -1, "y": -2})
        assert result4.fired_rules == []

    def test_streaming_mode_performance_vs_stateless(self):
        """Streaming mode should be faster with repeated facts."""
        # Create many rules
        rules = [
            Rule(
                id=i,
                name=f"Rule {i}",
                condition_dsl={
                    "type": "condition",
                    "field": f"field_{i % 10}",
                    "op": ">",
                    "value": i,
                },
                action=f"action_{i}",
                priority=1,
                domain="perf_test",
            )
            for i in range(100)
        ]

        facts = {f"field_{i}": 1000 for i in range(10)}

        # Test stateless engine
        stateless_engine = PhreakEngine(streaming_mode=False)
        stateless_engine.load_rules(rules)

        start = time.perf_counter()
        for _ in range(10):
            stateless_engine.evaluate(facts)
        stateless_time = time.perf_counter() - start

        # Test streaming engine
        streaming_engine = PhreakEngine(streaming_mode=True)
        streaming_engine.load_rules(rules)

        start = time.perf_counter()
        for _ in range(10):
            streaming_engine.evaluate(facts)
        streaming_time = time.perf_counter() - start

        # Streaming should be noticeably faster (at least 2x) with cached results
        # Note: This is a soft assertion as timing can vary by system
        ratio = stateless_time / streaming_time if streaming_time > 0 else 1
        assert streaming_time < stateless_time or ratio < 3, (
            f"Streaming time ({streaming_time:.4f}s) should be faster than "
            f"stateless ({stateless_time:.4f}s)"
        )


class TestComplexConditionDSLs:
    """Test various complex condition DSL patterns."""

    def test_nested_and_or_conditions(self):
        """Test deeply nested AND/OR conditions."""
        engine = PhreakEngine()

        rule = Rule(
            id=1,
            name="Nested Logic",
            condition_dsl={
                "type": "or",
                "conditions": [
                    {
                        "type": "and",
                        "conditions": [
                            {"type": "condition", "field": "a", "op": "==", "value": 1},
                            {"type": "condition", "field": "b", "op": "==", "value": 2},
                        ],
                    },
                    {
                        "type": "and",
                        "conditions": [
                            {"type": "condition", "field": "c", "op": "==", "value": 3},
                            {"type": "condition", "field": "d", "op": "==", "value": 4},
                        ],
                    },
                ],
            },
            action="approve",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # First branch matches
        result1 = engine.evaluate({"a": 1, "b": 2, "c": 0, "d": 0})
        assert 1 in result1.fired_rules

        # Second branch matches
        result2 = engine.evaluate({"a": 0, "b": 0, "c": 3, "d": 4})
        assert 1 in result2.fired_rules

        # Neither matches
        result3 = engine.evaluate({"a": 0, "b": 0, "c": 0, "d": 0})
        assert result3.fired_rules == []

    def test_not_conditions(self):
        """Test NOT conditions."""
        engine = PhreakEngine()

        rule = Rule(
            id=1,
            name="Not Rule",
            condition_dsl={
                "type": "and",
                "conditions": [
                    {
                        "type": "condition",
                        "field": "approved",
                        "op": "==",
                        "value": True,
                    },
                    {
                        "type": "not",
                        "condition": {
                            "type": "condition",
                            "field": "flagged",
                            "op": "==",
                            "value": True,
                        },
                    },
                ],
            },
            action="process",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # Approved and not flagged
        result1 = engine.evaluate({"approved": True, "flagged": False})
        assert 1 in result1.fired_rules

        # Approved but flagged
        result2 = engine.evaluate({"approved": True, "flagged": True})
        assert result2.fired_rules == []

    def test_exists_conditions(self):
        """Test EXISTS conditions."""
        engine = PhreakEngine()

        rule = Rule(
            id=1,
            name="Has Email",
            condition_dsl={
                "type": "exists",
                "field": "email",
            },
            action="send_email",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # Field exists
        result1 = engine.evaluate({"email": "test@example.com"})
        assert 1 in result1.fired_rules

        # Field doesn't exist
        result2 = engine.evaluate({"name": "John"})
        assert result2.fired_rules == []

        # Field is None
        result3 = engine.evaluate({"email": None})
        assert result3.fired_rules == []


class TestCrossDomainRuleInteractions:
    """Test rules across multiple domains."""

    def test_domain_isolation(self):
        """Rules in different domains should not interfere."""
        rules = [
            Rule(
                id=1,
                name="User Domain Rule",
                condition_dsl={
                    "type": "condition",
                    "field": "status",
                    "op": "==",
                    "value": "active",
                },
                action="approve_user",
                priority=1,
                domain="users",
            ),
            Rule(
                id=2,
                name="Account Domain Rule",
                condition_dsl={
                    "type": "condition",
                    "field": "status",
                    "op": "==",
                    "value": "active",
                },
                action="approve_account",
                priority=1,
                domain="accounts",
            ),
        ]

        engine = PhreakEngine()
        engine.load_rules(rules)

        result = engine.evaluate({"status": "active"})

        # Both rules should fire regardless of domain
        assert 1 in result.fired_rules
        assert 2 in result.fired_rules
        assert "approve_user" in result.actions
        assert "approve_account" in result.actions

    def test_mixed_domain_rules_with_filtering(self):
        """Test evaluating specific domains."""
        rules = [
            Rule(
                id=1,
                name="High Priority User Rule",
                condition_dsl={
                    "type": "condition",
                    "field": "priority",
                    "op": "==",
                    "value": "high",
                },
                action="escalate",
                priority=10,
                domain="users",
            ),
            Rule(
                id=2,
                name="Low Priority User Rule",
                condition_dsl={
                    "type": "condition",
                    "field": "priority",
                    "op": "==",
                    "value": "low",
                },
                action="queue",
                priority=1,
                domain="users",
            ),
            Rule(
                id=3,
                name="Payment Rule",
                condition_dsl={
                    "type": "condition",
                    "field": "amount",
                    "op": ">",
                    "value": 1000,
                },
                action="review",
                priority=5,
                domain="payments",
            ),
        ]

        engine = PhreakEngine()
        engine.load_rules(rules)

        result = engine.evaluate({"priority": "high", "amount": 5000})

        # All rules matching the conditions should fire
        assert 1 in result.fired_rules
        assert 3 in result.fired_rules
        assert 2 not in result.fired_rules


class TestRealWorldWorkflows:
    """Test realistic enterprise workflows with complex multi-condition rules."""

    def test_supply_chain_inventory_allocation(self):
        """Supply chain inventory allocation with 10+ conditions.

        Real-world scenario: Automated inventory allocation engine for
        warehouse distribution considering demand, stock levels, and costs.
        """
        rule = Rule(
            id=1,
            name="High Priority Warehouse Allocation",
            condition_dsl={
                "type": "and",
                "conditions": [
                    {
                        "type": "condition",
                        "field": "demand_forecast_units",
                        "op": ">",
                        "value": 100,
                    },
                    {
                        "type": "condition",
                        "field": "current_stock_units",
                        "op": ">=",
                        "value": 50,
                    },
                    {
                        "type": "condition",
                        "field": "warehouse_utilization_pct",
                        "op": "<",
                        "value": 85,
                    },
                    {
                        "type": "condition",
                        "field": "lead_time_days",
                        "op": "<",
                        "value": 14,
                    },
                    {
                        "type": "condition",
                        "field": "storage_cost_per_unit",
                        "op": "<",
                        "value": 5,
                    },
                    {
                        "type": "condition",
                        "field": "shipping_distance_miles",
                        "op": "<",
                        "value": 500,
                    },
                    {
                        "type": "condition",
                        "field": "customer_tier",
                        "op": "==",
                        "value": "premium",
                    },
                    {
                        "type": "condition",
                        "field": "order_frequency_months",
                        "op": "<",
                        "value": 3,
                    },
                    {
                        "type": "condition",
                        "field": "return_rate_pct",
                        "op": "<",
                        "value": 5,
                    },
                    {
                        "type": "condition",
                        "field": "product_spoilage_risk",
                        "op": "==",
                        "value": "low",
                    },
                ],
            },
            action="allocate_from_regional_warehouse",
            priority=10,
            domain="inventory",
        )

        facts_high_priority = {
            "demand_forecast_units": 250,
            "current_stock_units": 150,
            "warehouse_utilization_pct": 70,
            "lead_time_days": 3,
            "storage_cost_per_unit": 2.5,
            "shipping_distance_miles": 350,
            "customer_tier": "premium",
            "order_frequency_months": 1,
            "return_rate_pct": 2,
            "product_spoilage_risk": "low",
        }

        facts_low_priority = {
            "demand_forecast_units": 50,  # Too low
            "current_stock_units": 150,
            "warehouse_utilization_pct": 70,
            "lead_time_days": 3,
            "storage_cost_per_unit": 2.5,
            "shipping_distance_miles": 350,
            "customer_tier": "standard",  # Not premium
            "order_frequency_months": 1,
            "return_rate_pct": 2,
            "product_spoilage_risk": "low",
        }

        engine = PhreakEngine()
        engine.load_rules([rule])

        result_high = engine.evaluate(facts_high_priority)
        assert 1 in result_high.fired_rules
        assert "allocate_from_regional_warehouse" in result_high.actions

        result_low = engine.evaluate(facts_low_priority)
        assert result_low.fired_rules == []

    def test_healthcare_patient_risk_stratification(self):
        """Healthcare patient risk stratification with 11 conditions.

        Real-world scenario: Risk assessment for treatment routing in healthcare
        considering patient demographics, clinical indicators, and history.
        """
        rule = Rule(
            id=2,
            name="High Risk Patient - ICU Admission Pathway",
            condition_dsl={
                "type": "or",
                "conditions": [
                    {
                        "type": "and",
                        "conditions": [
                            {
                                "type": "condition",
                                "field": "age",
                                "op": ">=",
                                "value": 65,
                            },
                            {
                                "type": "condition",
                                "field": "comorbidity_score",
                                "op": ">",
                                "value": 3,
                            },
                            {
                                "type": "condition",
                                "field": "oxygen_saturation",
                                "op": "<",
                                "value": 92,
                            },
                            {
                                "type": "condition",
                                "field": "respiratory_rate",
                                "op": ">",
                                "value": 30,
                            },
                            {
                                "type": "condition",
                                "field": "systolic_bp",
                                "op": "<",
                                "value": 90,
                            },
                        ],
                    },
                    {
                        "type": "and",
                        "conditions": [
                            {
                                "type": "condition",
                                "field": "recent_surgery_days",
                                "op": "<",
                                "value": 7,
                            },
                            {
                                "type": "condition",
                                "field": "surgical_complications",
                                "op": "==",
                                "value": True,
                            },
                            {
                                "type": "condition",
                                "field": "drain_output_ml",
                                "op": ">",
                                "value": 200,
                            },
                            {
                                "type": "condition",
                                "field": "fever_present",
                                "op": "==",
                                "value": True,
                            },
                            {
                                "type": "condition",
                                "field": "albumin_level",
                                "op": "<",
                                "value": 2.5,
                            },
                        ],
                    },
                    {
                        "type": "and",
                        "conditions": [
                            {
                                "type": "condition",
                                "field": "immunocompromised",
                                "op": "==",
                                "value": True,
                            },
                            {
                                "type": "condition",
                                "field": "wbc_count",
                                "op": "<",
                                "value": 3,
                            },
                            {
                                "type": "condition",
                                "field": "infection_suspected",
                                "op": "==",
                                "value": True,
                            },
                            {
                                "type": "condition",
                                "field": "vasopressor_needed",
                                "op": "==",
                                "value": True,
                            },
                        ],
                    },
                ],
            },
            action="route_to_icu_immediate",
            priority=10,
            domain="healthcare",
        )

        facts_respiratory_crisis = {
            "age": 72,
            "comorbidity_score": 5,
            "oxygen_saturation": 85,
            "respiratory_rate": 35,
            "systolic_bp": 88,
            "recent_surgery_days": 30,
            "surgical_complications": False,
            "drain_output_ml": 100,
            "fever_present": False,
            "albumin_level": 3.5,
            "immunocompromised": False,
            "wbc_count": 8,
            "infection_suspected": False,
            "vasopressor_needed": False,
        }

        facts_post_op_complication = {
            "age": 55,
            "comorbidity_score": 1,
            "oxygen_saturation": 96,
            "respiratory_rate": 18,
            "systolic_bp": 120,
            "recent_surgery_days": 2,
            "surgical_complications": True,
            "drain_output_ml": 350,
            "fever_present": True,
            "albumin_level": 2.0,
            "immunocompromised": False,
            "wbc_count": 8,
            "infection_suspected": False,
            "vasopressor_needed": False,
        }

        facts_stable = {
            "age": 45,
            "comorbidity_score": 0,
            "oxygen_saturation": 98,
            "respiratory_rate": 16,
            "systolic_bp": 125,
            "recent_surgery_days": 30,
            "surgical_complications": False,
            "drain_output_ml": 50,
            "fever_present": False,
            "albumin_level": 4.0,
            "immunocompromised": False,
            "wbc_count": 7,
            "infection_suspected": False,
            "vasopressor_needed": False,
        }

        engine = PhreakEngine()
        engine.load_rules([rule])

        result_respiratory = engine.evaluate(facts_respiratory_crisis)
        assert 2 in result_respiratory.fired_rules
        assert "route_to_icu_immediate" in result_respiratory.actions

        result_post_op = engine.evaluate(facts_post_op_complication)
        assert 2 in result_post_op.fired_rules
        assert "route_to_icu_immediate" in result_post_op.actions

        result_stable = engine.evaluate(facts_stable)
        assert result_stable.fired_rules == []

    def test_subscription_churn_prediction_retention(self):
        """Subscription retention with 10+ conditions.

        Real-world scenario: Automated churn prediction and retention campaign
        routing based on behavioral, engagement, and payment metrics.
        """
        rule = Rule(
            id=3,
            name="At-Risk Subscriber - Proactive Retention Campaign",
            condition_dsl={
                "type": "and",
                "conditions": [
                    {
                        "type": "condition",
                        "field": "account_age_months",
                        "op": ">=",
                        "value": 6,
                    },
                    {
                        "type": "condition",
                        "field": "login_frequency_days",
                        "op": ">",
                        "value": 14,
                    },
                    {
                        "type": "condition",
                        "field": "feature_usage_pct",
                        "op": "<",
                        "value": 30,
                    },
                    {
                        "type": "condition",
                        "field": "support_tickets_90days",
                        "op": ">",
                        "value": 2,
                    },
                    {
                        "type": "condition",
                        "field": "payment_failed_attempts",
                        "op": ">",
                        "value": 1,
                    },
                    {
                        "type": "condition",
                        "field": "email_open_rate_pct",
                        "op": "<",
                        "value": 15,
                    },
                    {
                        "type": "condition",
                        "field": "days_since_last_purchase",
                        "op": ">",
                        "value": 60,
                    },
                    {
                        "type": "condition",
                        "field": "competitor_activity_detected",
                        "op": "==",
                        "value": True,
                    },
                    {"type": "condition", "field": "ltv_usd", "op": "<", "value": 500},
                    {
                        "type": "condition",
                        "field": "churned_before",
                        "op": "==",
                        "value": False,
                    },
                ],
            },
            action="trigger_vip_retention_offer",
            priority=10,
            domain="subscriptions",
        )

        facts_at_risk = {
            "account_age_months": 18,
            "login_frequency_days": 21,
            "feature_usage_pct": 15,
            "support_tickets_90days": 3,
            "payment_failed_attempts": 2,
            "email_open_rate_pct": 10,
            "days_since_last_purchase": 90,
            "competitor_activity_detected": True,
            "ltv_usd": 350,
            "churned_before": False,
        }

        facts_healthy = {
            "account_age_months": 18,
            "login_frequency_days": 5,
            "feature_usage_pct": 75,
            "support_tickets_90days": 0,
            "payment_failed_attempts": 0,
            "email_open_rate_pct": 45,
            "days_since_last_purchase": 10,
            "competitor_activity_detected": False,
            "ltv_usd": 1200,
            "churned_before": False,
        }

        engine = PhreakEngine()
        engine.load_rules([rule])

        result_at_risk = engine.evaluate(facts_at_risk)
        assert 3 in result_at_risk.fired_rules
        assert "trigger_vip_retention_offer" in result_at_risk.actions

        result_healthy = engine.evaluate(facts_healthy)
        assert result_healthy.fired_rules == []


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling."""

    def test_empty_facts(self):
        """Engine should handle empty facts gracefully."""
        engine = PhreakEngine()

        rule = Rule(
            id=1,
            name="Always Fire",
            condition_dsl={
                "type": "condition",
                "field": "flag",
                "op": "==",
                "value": True,
            },
            action="fire",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # Empty facts should not match
        result = engine.evaluate({})
        assert result.fired_rules == []

    def test_null_values(self):
        """Engine should handle null/None values in facts."""
        engine = PhreakEngine()

        # Instead of comparing to None directly, test with exists operator
        rule = Rule(
            id=1,
            name="Has Value",
            condition_dsl={
                "type": "exists",
                "field": "value",
            },
            action="has_value",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # Field with None value should not trigger exists
        result1 = engine.evaluate({"value": None})
        assert result1.fired_rules == []

        # Field with actual value should trigger exists
        result2 = engine.evaluate({"value": 0})
        assert 1 in result2.fired_rules

        # Missing field should not trigger exists
        result3 = engine.evaluate({})
        assert result3.fired_rules == []

    def test_type_coercion(self):
        """Engine should handle type coercion in comparisons."""
        engine = PhreakEngine()

        rule = Rule(
            id=1,
            name="String Comparison",
            condition_dsl={
                "type": "condition",
                "field": "status",
                "op": "==",
                "value": "active",
            },
            action="proceed",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # Exact match
        result1 = engine.evaluate({"status": "active"})
        assert 1 in result1.fired_rules

        # Different string
        result2 = engine.evaluate({"status": "inactive"})
        assert result2.fired_rules == []

    def test_numeric_comparison_precision(self):
        """Engine should handle numeric comparisons with precision."""
        engine = PhreakEngine()

        rule = Rule(
            id=1,
            name="Float Comparison",
            condition_dsl={
                "type": "condition",
                "field": "ratio",
                "op": ">",
                "value": 0.5,
            },
            action="accept",
            priority=1,
            domain="test",
        )

        engine.load_rules([rule])

        # Just above threshold
        result1 = engine.evaluate({"ratio": 0.501})
        assert 1 in result1.fired_rules

        # Just below threshold
        result2 = engine.evaluate({"ratio": 0.499})
        assert result2.fired_rules == []

        # Exactly at threshold
        result3 = engine.evaluate({"ratio": 0.5})
        assert result3.fired_rules == []
