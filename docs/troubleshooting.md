# Troubleshooting

**Prerequisites:** [API](api.md) and [Deployment](deployment.md).

---

Common issues and solutions.

## API server won't start

**Problem:** `Address already in use` or connection refused.

**Solution:**
```bash
# Check if port 8000 is in use
lsof -i :8000

# Use a different port
python -m fluxrules.api.app --port 8001
```

## Rules not matching

**Problem:** Expected rule matches, but `fired_rules` is empty.

**Solutions:**
1. **Validate condition tree syntax:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/validate \
     -H "Content-Type: application/json" \
     -d '{"conditions": {...}}'
   ```

2. **Check fact format:** Ensure fact keys match condition field names
```python
# python skip
   from fluxrules import F, Rule
   
   # Rule expects "amount" field
   rule = Rule(
       conditions=F("amount") > 5000
   )
   
   # Fact must have "amount"
   result = engine.evaluate({"amount": 7500})  # ✓ Works
   result = engine.evaluate({"value": 7500})   # ✗ Won't match
   ```

   If the fact carries the field under another key style (`user_age` for a
   rule on `userAge`), evaluation raises `FieldNotFoundError` naming the key
   it found. Rename the rule field, or declare a
   [fact schema](typed-facts.md) with `lenient_aliases()` and
   `validate_facts="normalize"` so incoming keys are renamed for you.

3. **Check operator:** Verify operator spelling and case
   - Valid: `"=="`, `"!="`, `">"`, `"<"`, `"in"`, `"contains"`

## A NOT rule fires unexpectedly, or warns `MissingFieldNotWarning`

**Problem:** A rule such as `~(F("blocked") == True)` fires for facts that do
not carry `blocked` at all, and a `MissingFieldNotWarning` is logged.

**Cause:** A missing field makes its condition `False`, so `NOT` over it is
`True`. From 2.0 such a `NOT` will not fire.

**Solutions:**
- Opt in to the 2.0 behaviour now: `EngineConfig(missing_field="unknown")`.
- If firing on absence is intended, say so with `~F("blocked").exists() | ~(F("blocked") == True)`
  and set `missing_field="false"` to silence the warning.

See [Missing fields and NOT](conditions.md#missing-fields-and-not).

## `UnknownFieldError` from `load_rules`

**Problem:** `load_rules` raises `UnknownFieldError: Rule '...' references unknown field ...`.

**Cause:** The engine was built with `fact_schema=Model` and a rule names a
field the model does not have. Nothing was loaded.

**Solution:** Fix the rule field (the message suggests the closest name), or
add the field to the model. Nested models are addressed with dotted paths
(`customer.age`).

## High latency

**Problem:** Evaluations are slow.

**Solutions:**
1. **Filter rules by domain/tags:** Evaluate only the rules that apply to the fact
2. **Profile with latency_ms:** Check the returned latency
3. **Reduce rule complexity:** Simpler conditions evaluate faster

## Memory leaks

**Problem:** Memory usage keeps growing.

**Solutions:**
1. **Use PHREAK (default):** Lower memory footprint
2. **Check working_memory:** If asserting many facts, retract old ones
   ```python
   fact_id = engine.assert_fact(fact)
   # Later
   engine.retract_fact(fact_id)
   ```

## Database connection errors

**Problem:** `connection refused` or `database unavailable`.

**Solutions:**
```bash
# Check connection string
echo $DATABASE_URL

# Test database connectivity
psql -h db.example.com -U user -d fluxrules -c "SELECT 1"

# Use fallback (in-memory mode)
export FLUXRULES_FALLBACK_MODE=true
```

---

## Next Steps

- **Security**: See [Security](security.md) for authentication
- **Observability**: See [Observability](observability.md) for monitoring
