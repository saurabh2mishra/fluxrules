#!/bin/bash
# Demo script: Audit Policy & Reports workflow
set -e

BASE="http://127.0.0.1:8099/api/v1"

echo "=== Getting admin token ==="
TOKEN=$(curl -s -X POST "$BASE/auth/token" \
  -d 'username=demoadmin&password=DemoP@ss123!' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token obtained: ${TOKEN:0:20}..."
echo ""

AUTH="Authorization: Bearer $TOKEN"

echo "============================================"
echo "  STEP 1: Create Audit Policies"
echo "============================================"
echo ""

echo "--- Policy 1: Nightly Full Audit ---"
curl -s -X POST "$BASE/admin/audit-policy" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "name": "Nightly Full Audit",
    "description": "Runs ALL checks every night at 2 AM UTC",
    "cron_expression": "0 2 * * *",
    "scope": "all",
    "enabled": true
  }' | python3 -m json.tool
echo ""

echo "--- Policy 2: Hourly Integrity Check ---"
curl -s -X POST "$BASE/admin/audit-policy" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "name": "Hourly Integrity Check",
    "description": "Verifies audit log HMAC integrity every hour",
    "cron_expression": "0 * * * *",
    "scope": "integrity",
    "enabled": true
  }' | python3 -m json.tool
echo ""

echo "============================================"
echo "  STEP 2: List All Audit Policies"
echo "============================================"
curl -s "$BASE/admin/audit-policy" -H "$AUTH" | python3 -m json.tool
echo ""

echo "============================================"
echo "  STEP 3: Trigger a Manual Audit Run (all)"
echo "============================================"
curl -s -X POST "$BASE/admin/audit-run" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"scope": "all"}' | python3 -m json.tool
echo ""

echo "============================================"
echo "  STEP 4: Trigger Targeted Runs"
echo "============================================"

echo "--- Run: coverage + rule_health only ---"
curl -s -X POST "$BASE/admin/audit-run" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"scope": "coverage,rule_health"}' | python3 -m json.tool
echo ""

echo "--- Run: retention only ---"
curl -s -X POST "$BASE/admin/audit-run" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"scope": "retention"}' | python3 -m json.tool
echo ""

echo "============================================"
echo "  STEP 5: List All Audit Reports"
echo "============================================"
curl -s "$BASE/admin/audit-report" -H "$AUTH" | python3 -m json.tool
echo ""

echo "============================================"
echo "  STEP 6: Get Full Report Details (ID=1)"
echo "============================================"
curl -s "$BASE/admin/audit-report/1" -H "$AUTH" | python3 -m json.tool
echo ""

echo "============================================"
echo "  STEP 7: Filter Reports by Status"
echo "============================================"
echo "--- Passed reports ---"
curl -s "$BASE/admin/audit-report?status=passed" -H "$AUTH" | python3 -m json.tool
echo ""

echo "============================================"
echo "  STEP 8: Update a Policy (disable it)"
echo "============================================"
curl -s -X PATCH "$BASE/admin/audit-policy/2" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"enabled": false}' | python3 -m json.tool
echo ""

echo "============================================"
echo "  DONE! All audit report features demonstrated."
echo "============================================"
