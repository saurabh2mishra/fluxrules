#!/usr/bin/env python3
"""Comprehensive API endpoint testing with authentication support.

Tests all FluxRules API endpoints with proper auth handling and endpoint discovery.
"""

import asyncio
import sys

import httpx

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RESET = "\033[0m"

BASE_URL = "http://localhost:8000"


async def get_token(client: httpx.AsyncClient) -> str | None:
    """Try to get an authentication token."""
    try:
        # First try to register
        register_response = await client.post(
            f"{BASE_URL}/api/v1/auth/register",
            json={
                "username": "testuser",
                "password": "testpass123",
                "email": "test@example.com",
            },
        )
        print(f"  Register response: {register_response.status_code}")

        # Try to get token
        token_response = await client.post(
            f"{BASE_URL}/api/v1/auth/token",
            data={"username": "testuser", "password": "testpass123"},
        )
        print(f"  Token response: {token_response.status_code}")

        if token_response.status_code == 200:
            data = token_response.json()
            return data.get("access_token")
    except Exception as e:
        print(f"  Could not get token: {e}")

    return None


async def discover_endpoints() -> dict:
    """Discover available endpoints from OpenAPI docs."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/openapi.json")
            if response.status_code == 200:
                docs = response.json()
                endpoints = {}

                for path, methods in docs.get("paths", {}).items():
                    for method, details in methods.items():
                        if method.lower() in ["get", "post", "put", "delete", "patch"]:
                            tags = details.get("tags", ["Other"])
                            category = tags[0] if tags else "Other"

                            if category not in endpoints:
                                endpoints[category] = []

                            endpoints[category].append(
                                {
                                    "method": method.upper(),
                                    "path": path,
                                    "requires_auth": "security" in details
                                    and details["security"] is not None,
                                }
                            )

                return endpoints
    except Exception as e:
        print(f"{RED}Error discovering endpoints: {e}{RESET}")

    return {}


async def test_endpoint(
    client: httpx.AsyncClient, method: str, path: str, token: str | None = None
) -> dict:
    """Test a single endpoint."""
    try:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"{BASE_URL}{path}"

        if method == "GET":
            response = await client.get(url, headers=headers)
        elif method == "POST":
            response = await client.post(url, headers=headers, json={})
        elif method == "PUT":
            response = await client.put(url, headers=headers, json={})
        elif method == "DELETE":
            response = await client.delete(url, headers=headers)
        elif method == "PATCH":
            response = await client.patch(url, headers=headers, json={})
        else:
            return {
                "path": path,
                "method": method,
                "status": "unknown",
                "status_code": -1,
            }

        return {
            "path": path,
            "method": method,
            "status_code": response.status_code,
            "status": "ok" if response.status_code < 500 else "error",
        }
    except Exception as e:
        return {
            "path": path,
            "method": method,
            "status": "error",
            "status_code": -1,
            "error": str(e),
        }


async def run_tests():
    """Run all endpoint tests."""
    print(f"\n{BLUE}{'=' * 90}")
    print("FLUXRULES API ENDPOINT DISCOVERY & TESTING")
    print(f"{'=' * 90}{RESET}\n")

    # Check if server is running
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f"{BASE_URL}/health", timeout=5.0)
            print(f"{GREEN}✓{RESET} API server is running at {BASE_URL}\n")
    except Exception as e:
        print(f"{RED}✗{RESET} Cannot connect to API server at {BASE_URL}")
        print(f"{RED}Error: {e}{RESET}\n")
        return 1

    # Discover endpoints from OpenAPI
    print(f"{BLUE}Discovering endpoints from OpenAPI documentation...{RESET}\n")
    endpoints = await discover_endpoints()

    if not endpoints:
        print(f"{YELLOW}No endpoints found in OpenAPI docs{RESET}\n")
        return 1

    total_endpoints = sum(len(v) for v in endpoints.values())
    print(f"{GREEN}✓{RESET} Found {total_endpoints} endpoints across {len(endpoints)} categories\n")

    # Try to get auth token
    print(f"{BLUE}Attempting to get authentication token...{RESET}\n")
    token = None
    async with httpx.AsyncClient() as client:
        token = await get_token(client)

    if token:
        print(f"{GREEN}✓{RESET} Successfully obtained authentication token\n")
    else:
        print(f"{YELLOW}⚠{RESET} Could not obtain auth token - some endpoints may return 401\n")

    # Test endpoints by category
    print(f"{BLUE}{'=' * 90}")
    print("TESTING ENDPOINTS BY CATEGORY")
    print(f"{'=' * 90}{RESET}\n")

    results = {}
    total_passed = 0
    total_endpoints_count = 0

    async with httpx.AsyncClient(timeout=10.0) as client:
        for category in sorted(endpoints.keys()):
            category_endpoints = endpoints[category]
            print(f"{YELLOW}{category}{RESET} ({len(category_endpoints)} endpoints)")

            results[category] = {
                "passed": 0,
                "failed": 0,
                "total": len(category_endpoints),
            }

            for endpoint_info in category_endpoints:
                method = endpoint_info["method"]
                path = endpoint_info["path"]
                requires_auth = endpoint_info["requires_auth"]

                total_endpoints_count += 1

                # Use token if endpoint requires auth and we have it
                test_token = token if requires_auth else None

                result = await test_endpoint(client, method, path, test_token)
                status_code = result["status_code"]

                # Determine if test passed
                # 2xx and 4xx are "ok" (successful request), 5xx are errors
                passed = 200 <= status_code < 500

                if passed:
                    results[category]["passed"] += 1
                    total_passed += 1
                    status_symbol = f"{GREEN}✓{RESET}"
                else:
                    status_symbol = f"{RED}✗{RESET}"

                print(f"  {status_symbol} {method:6s} {path:50s} [{status_code}]")

            print()

    # Summary
    print(f"{BLUE}{'=' * 90}")
    print("SUMMARY BY CATEGORY")
    print(f"{'=' * 90}{RESET}\n")

    for category in sorted(results.keys()):
        counts = results[category]
        pct = (counts["passed"] / counts["total"] * 100) if counts["total"] > 0 else 0
        status = (
            f"{GREEN}✓{RESET}"
            if counts["passed"] == counts["total"]
            else f"{YELLOW}⚠{RESET}"
            if counts["passed"] > 0
            else f"{RED}✗{RESET}"
        )
        print(f"{status} {category:30s} {counts['passed']:3d}/{counts['total']:3d} ({pct:5.1f}%)")

    print(f"\n{BLUE}{'=' * 90}")
    print(
        f"TOTAL: {total_passed}/{total_endpoints_count} endpoints working ({total_passed / total_endpoints_count * 100:.1f}%)"
    )
    print(f"{'=' * 90}{RESET}\n")

    if total_passed == total_endpoints_count:
        print(f"{GREEN}✓ All endpoints are working correctly!{RESET}\n")
        return 0
    elif total_passed > 0:
        print(f"{YELLOW}⚠ Most endpoints are working. Check failures above for details.{RESET}\n")
        return 0
    else:
        print(f"{RED}✗ Most endpoints failed. Check the output above.{RESET}\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)
