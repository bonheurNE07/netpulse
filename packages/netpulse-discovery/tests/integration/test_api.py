import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from netpulse.discovery.api import discovery_router

# Create a minimal app to test the router
app = FastAPI()
app.include_router(discovery_router)

client = TestClient(app)

def test_scan_endpoint_valid_network():
    response = client.post(
        "/discovery/scan",
        json={"target": "127.0.0.1/32", "timeout_ms": 100}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["network"] == "127.0.0.1/32"
    assert "devices" in data

def test_scan_endpoint_invalid_network():
    response = client.post(
        "/discovery/scan",
        json={"target": "invalid-network", "timeout_ms": 100}
    )
    assert response.status_code == 500
    assert "Invalid network" in response.json()["detail"]
