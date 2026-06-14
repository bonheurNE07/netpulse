import pytest
from fastapi.testclient import TestClient
from netpulse.subnet.api import app


def test_api_subnet_info_success():
    """Verify standard subnet info endpoint returns 200 and correct parameters."""
    client = TestClient(app)
    payload = {
        "ip": "192.168.1.50",
        "mask_or_prefix": "24"
    }
    response = client.post("/api/v1/subnet/info", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["ip"] == "192.168.1.50"
    assert data["network_cidr"] == "192.168.1.0/24"
    assert data["prefix_length"] == 24
    assert data["netmask"] == "255.255.255.0"
    assert data["total_hosts"] == 254
    assert "binary_representation" in data


def test_api_subnet_info_invalid():
    """Verify info endpoint raises HTTP 400 for bad IPs or prefix ranges."""
    client = TestClient(app)
    payload = {
        "ip": "192.168.1.50",
        "mask_or_prefix": "99"  # Invalid prefix
    }
    response = client.post("/api/v1/subnet/info", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "InvalidSubnetParameters"


def test_api_subnet_split_count_success():
    """Verify split endpoint splits networks into fixed partitions correctly."""
    client = TestClient(app)
    payload = {
        "parent_network": "192.168.1.0/24",
        "subnets_count": 4
    }
    response = client.post("/api/v1/subnet/split", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4
    assert data[0] == "192.168.1.0/26"
    assert data[3] == "192.168.1.192/26"


def test_api_subnet_split_invalid():
    """Verify split endpoint raises HTTP 400 for impossible boundaries."""
    client = TestClient(app)
    payload = {
        "parent_network": "192.168.1.0/30",
        "hosts_per_subnet": 50  # Parent is too small
    }
    response = client.post("/api/v1/subnet/split", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "SubnetSplitError"


def test_api_subnet_vlsm_success():
    """Verify VLSM endpoint returns valid allocation schedules and statistics."""
    client = TestClient(app)
    payload = {
        "parent_network": "192.168.1.0/24",
        "requirements": [
            {"name": "HR", "hosts": 120},
            {"name": "Dev", "hosts": 50}
        ]
    }
    response = client.post("/api/v1/subnet/vlsm", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["parent_network"] == "192.168.1.0/24"
    assert len(data["allocations"]) == 2
    
    # HR is allocated 128 block size (/25)
    # Dev is allocated 64 block size (/26)
    allocs = {a["name"]: a for a in data["allocations"]}
    assert allocs["HR"]["network_cidr"].endswith("/25")
    assert allocs["Dev"]["network_cidr"].endswith("/26")
    assert not data["unallocated_requirements"]


def test_api_subnet_vlsm_invalid():
    """Verify VLSM endpoint returns HTTP 400 for bad parent networks."""
    client = TestClient(app)
    payload = {
        "parent_network": "invalid-cidr",
        "requirements": [{"name": "HR", "hosts": 120}]
    }
    response = client.post("/api/v1/subnet/vlsm", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "VLSMAllocationError"


def test_api_subnet_discover_success():
    """Verify discover endpoint matches IP against candidate ranges correctly."""
    client = TestClient(app)
    payload = {
        "ip": "192.168.1.45",
        "subnets": ["192.168.1.0/26", "192.168.1.64/26"]
    }
    response = client.post("/api/v1/subnet/discover", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["ip"] == "192.168.1.45"
    assert data["containing_subnet"] == "192.168.1.0/26"


def test_api_subnet_discover_none():
    """Verify discover endpoint returns null if no containing range matches."""
    client = TestClient(app)
    payload = {
        "ip": "10.0.0.1",
        "subnets": ["192.168.1.0/26"]
    }
    response = client.post("/api/v1/subnet/discover", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["containing_subnet"] is None


def test_api_subnet_discover_invalid():
    """Verify discover endpoint raises HTTP 400 for malformed target IP."""
    client = TestClient(app)
    payload = {
        "ip": "malformed-ip",
        "subnets": ["192.168.1.0/26"]
    }
    response = client.post("/api/v1/subnet/discover", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "SubnetLookupError"
