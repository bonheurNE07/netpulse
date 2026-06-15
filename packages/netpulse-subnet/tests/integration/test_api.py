import pytest
from fastapi.testclient import TestClient
from netpulse.subnet.api import app

client = TestClient(app)

def test_api_subnet_info_ipv4():
    response = client.post("/api/v1/subnet/info", json={
        "ip": "192.168.1.50",
        "mask_or_prefix": "24"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["network_cidr"] == "192.168.1.0/24"
    assert data["broadcast_address"] == "192.168.1.255"
    assert data["total_hosts"] == 254

def test_api_subnet_info_ipv6():
    response = client.post("/api/v1/subnet/info", json={
        "ip": "2001:db8::1",
        "mask_or_prefix": "64"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["network_cidr"] == "2001:db8::/64"
    assert data["broadcast_address"] is None

def test_api_subnet_split():
    response = client.post("/api/v1/subnet/split", json={
        "parent_network": "10.0.0.0/8",
        "subnets_count": 4
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4
    assert data[0] == "10.0.0.0/10"

def test_api_subnet_vlsm():
    response = client.post("/api/v1/subnet/vlsm", json={
        "parent_network": "192.168.1.0/24",
        "requirements": [
            {"name": "HR", "hosts": 100}
        ]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["parent_network"] == "192.168.1.0/24"
    assert len(data["allocations"]) == 1
    assert data["allocations"][0]["name"] == "HR"
    assert data["allocations"][0]["network_cidr"] == "192.168.1.0/25"

def test_api_subnet_discover():
    response = client.post("/api/v1/subnet/discover", json={
        "ip": "192.168.1.50",
        "subnets": ["192.168.1.0/26", "192.168.1.64/26"]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["containing_subnet"] == "192.168.1.0/26"

def test_api_subnet_validate():
    response = client.post("/api/v1/subnet/validate", json={
        "subnets": ["192.168.1.0/24", "192.168.1.128/25"],
        "parent_network": "192.168.1.0/23"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["has_overlaps"] is True
    assert len(data["overlaps"]) == 1
    assert data["overlaps"][0]["subnet1"] == "192.168.1.0/24"
    assert data["overlaps"][0]["subnet2"] == "192.168.1.128/25"
    assert data["free_space"] == ["192.168.0.0/24"]

def test_api_subnet_summarize():
    response = client.post("/api/v1/subnet/summarize", json={
        "subnets": ["10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["supernet"] == "10.0.0.0/22"
    assert data["has_slack"] is False
    assert data["slack_ips"] == 0
