# Choosing an Evaluation Mode

**Prerequisites:** [The FluxRules Engine](engine-comparison.md).

---

FluxRules ships a single engine (PHREAK), so there is no engine to pick. The one
decision you make is which **evaluation mode** fits your workload.

## Decision flowchart

1. **Do you keep state between facts?**
   - No — each request is independent → **Stateless mode** (default)
   - Yes — you assert/retract into a long-lived session → **Streaming mode**

2. **What is the evaluation pattern?**
   - Request-response (HTTP) → **Stateless mode**
   - Batch (many independent facts) → **Stateless mode**
   - Event stream where only changes matter → **Streaming mode**

3. **Do you need per-fact deltas?**
   - No, you want the full fired set every call → **Stateless mode**
   - Yes, you want only what changed since the last fact → **Streaming mode**

## Quick decision guide

| Scenario | Mode |
|----------|------|
| HTTP API for fraud scoring | **Stateless** |
| Batch data pipeline | **Stateless** |
| Rules updated daily | **Stateless** (reload rules) |
| Single-file rule config | **Stateless** |
| Long-lived session with retractions | **Streaming** |
| Event stream, deltas only | **Streaming** |

## Default recommendation

**Use stateless mode** unless you specifically need persistent working memory:

- Simplest deployment and reasoning (no state to manage)
- Lowest memory footprint (nothing retained between calls)
- Ideal for request-response and batch workloads

Enable streaming only when you need incremental deltas across a session.

---

## Next Steps

- **The FluxRules Engine** — See [The FluxRules Engine](engine-comparison.md) for how the modes work
- **Working Memory** — See [Working Memory](working-memory.md) for the streaming contract
- **Concepts** — See [Concepts](concepts.md) for engine fundamentals
