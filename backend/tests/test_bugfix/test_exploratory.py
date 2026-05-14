"""
Exploratory Bug Condition Tests
================================

These tests are run against UNFIXED code to confirm root causes.
They are EXPECTED TO FAIL on unfixed code — a failure here confirms the bug exists.

**Validates: Requirements 1.1**
"""

from __future__ import annotations

from app.api.router import api_router


def test_health_route_registered() -> None:
    """
    Assert that api_router contains a route with path /v1/health.

    This test is EXPECTED TO FAIL on unfixed code because the health router
    is not included in api_router in backend/app/api/router.py.
    A failure here confirms Bug 1.1: the health router is missing from api_router.

    **Validates: Requirements 1.1**
    """
    route_paths = [route.path for route in api_router.routes]
    assert "/v1/health" in route_paths, (
        f"Bug 1.1 confirmed: /v1/health is NOT registered in api_router. "
        f"Registered paths: {route_paths}"
    )
