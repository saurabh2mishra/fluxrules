# Use Cases

Real-world scenarios where FluxRules excels.

## Fraud Detection

**Scenario:** Bank processes transactions and needs to flag suspicious ones.

**Rules:**
- High-value transactions (>$10,000)
- Transactions from high-risk countries
- Unusual velocity (5+ transactions in 1 hour)
- Cross-border with high-risk IP

**FluxRules advantage:** Simple DSL for complex business logic, millisecond latency.

**Example:** [Example 22: Real-World Workflow](https://github.com/fluxrules/fluxrules/blob/main/examples/22_real_world_workflow.py)

## Compliance Automation

**Scenario:** E-commerce platform enforces compliance rules.

**Rules:**
- Block sales to restricted countries
- Require identity verification for large orders
- Flag duplicate customer accounts
- Require 2FA for high-value orders

**FluxRules advantage:** Rules externalized from code, changeable without deployment.

## Risk Scoring

**Scenario:** Insurance company scores claims automatically.

**Rules:**
- Tier 1: Low-risk claims (auto-approve)
- Tier 2: Medium-risk claims (manual review)
- Tier 3: High-risk claims (investigation)

**FluxRules advantage:** Tiered logic with explicit rule evaluation.

## Workflow Routing

**Scenario:** API gateway routes requests based on rules.

**Rules:**
- Route large requests to high-capacity workers
- Route priority customers to expedited queue
- Route test traffic to staging environment

**FluxRules advantage:** Fast (ms-level) routing decisions.

## Order Management

**Scenario:** E-commerce system automates order processing.

**Rules:**
- Orders < $100: Auto-ship
- Orders > $1000: Require approval
- International orders: Require customs clearance
- VIP orders: Rush shipping

**FluxRules advantage:** Multi-tier logic with conditional actions.

---

## Next Steps

- **Concepts** — See [Concepts](concepts.md) for fundamentals
- **Quickstart** — See [Quickstart](quickstart.md) to build your first rules
- **Examples** — See [Examples](examples.md) for working code
