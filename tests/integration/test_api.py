import pytest
import time
from unittest.mock import patch
from fastapi.testclient import TestClient

from netpulse_api.main import app, request_history
from netpulse.core.models.discovery import DiscoveryResult, DiscoveryMethod


@pytest.fixture(autouse=True)
def clean_rate_limit_history():
    """Clear rate limiting history between test runs."""
    request_history.clear()


def test_health_check():
    """Verify health check endpoint returns 200 and expected payload."""
    client = TestClient(app)
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "netpulse-api"
    assert "timestamp" in data


def test_security_headers():
    """Verify that every API response includes strict security headers."""
    client = TestClient(app)
    response = client.get("/health")
    
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Content-Security-Policy") == "default-src 'self';"


def test_cors_headers_allowed_origin():
    """Verify that CORS headers are returned for allowed origins."""
    client = TestClient(app)
    headers = {"Origin": "http://localhost:3000"}
    response = client.get("/health", headers=headers)
    
    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"


def test_cors_headers_disallowed_origin():
    """Verify that CORS headers are omitted/rejected for arbitrary origins."""
    client = TestClient(app)
    headers = {"Origin": "http://malicious.com"}
    response = client.get("/health", headers=headers)
    
    assert "Access-Control-Allow-Origin" not in response.headers


def test_discover_valid_subnet_mock():
    """Verify POST /api/v1/discover returns successful discovery in mock/fallback mode."""
    client = TestClient(app)
    payload = {
        "target_network": "172.19.57.0/24",
        "methods": ["icmp"],
        "timeout_ms": 2000
    }
    response = client.post("/api/v1/discover", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["network"] == "172.19.57.0/24"
    assert data["status"] in ["completed", "failed", "partial"]
    assert "devices" in data
    assert "stats" in data


def test_discover_invalid_cidr():
    """Verify POST /api/v1/discover rejects malformed networks with HTTP 422."""
    client = TestClient(app)
    payload = {
        "target_network": "999.999.999.999/24",
        "methods": ["arp"]
    }
    response = client.post("/api/v1/discover", json=payload)
    
    assert response.status_code == 422
    assert "Invalid network CIDR format" in response.text


def test_discover_invalid_method():
    """Verify POST /api/v1/discover rejects unsupported methods with HTTP 422."""
    client = TestClient(app)
    payload = {
        "target_network": "172.19.57.0/24",
        "methods": ["invalid_method_xyz"]
    }
    response = client.post("/api/v1/discover", json=payload)
    
    assert response.status_code == 422
    assert "Supported methods: 'arp', 'icmp'" in response.text


def test_api_rate_limiting():
    """Verify custom rate limiter allows at most 5 requests/min and returns 429 on the 6th."""
    client = TestClient(app)
    payload = {
        "target_network": "172.19.57.0/24",
        "methods": ["icmp"]
    }
    
    # First 5 calls must succeed (HTTP 200)
    for _ in range(5):
        response = client.post("/api/v1/discover", json=payload)
        assert response.status_code == 200
        
    # The 6th call must exceed the rate limit (HTTP 429)
    response_6 = client.post("/api/v1/discover", json=payload)
    assert response_6.status_code == 429
    data = response_6.json()
    assert data["detail"]["error"] == "RateLimitExceeded"
    assert "retry_after_seconds" in data["detail"]


def test_privilege_error_translation():
    """Verify that low-level raw socket PermissionErrors are translated to structured HTTP 500."""
    client = TestClient(app)
    payload = {
        "target_network": "172.19.57.0/24",
        "methods": ["arp"]
    }
    
    # We mock discover_network to return a result containing a permission denied error
    mock_result = DiscoveryResult(
        network="172.19.57.0/24",
        methods=[DiscoveryMethod.ARP],
        status="failed",
        errors=["arp scan failed: Permission Denied: Failed to open raw datalink interface."],
        devices=[],
        started_at="2026-05-22T20:47:32.256435Z",
        finished_at="2026-05-22T20:47:32.257303Z",
        stats={"scanned": 256, "responsive": 0}
    )
    
    with patch("netpulse_api.main.DiscoveryService.discover_network") as mock_discover:
        mock_discover.return_value = mock_result
        
        response = client.post("/api/v1/discover", json=payload)
        
        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["error"] == "PrivilegeError"
        assert "requires elevated privileges" in data["detail"]["message"]
        assert "sudo_run" in data["detail"]["remediation"]
        assert "setcap_grant" in data["detail"]["remediation"]
        assert "mock_mode" in data["detail"]["remediation"]
