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
1. **Validate DSL syntax:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/validate \
     -H "Content-Type: application/json" \
     -d '{"condition_dsl": {...}}'
   ```

2. **Check fact format:** Ensure fact keys match condition field names
```python python skip
   from fluxrules import Rule
   
   # Rule expects "amount" field
   rule = Rule(
       condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000}
   )
   
   # Fact must have "amount"
   result = engine.evaluate({"amount": 7500})  # ✅ Works
   result = engine.evaluate({"value": 7500})   # ❌ Won't match
   ```

3. **Check operator:** Verify operator spelling and case
   - Valid: `"=="`, `"!="`, `">"`, `"<"`, `"in"`, `"contains"`

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

- **Security** — See [Security](security.md) for authentication
- **Observability** — See [Observability](observability.md) for monitoring
