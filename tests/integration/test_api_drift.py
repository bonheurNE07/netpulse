import pytest
import uuid
from fastapi.testclient import TestClient

from netpulse_api.main import app, db_service
from netpulse.discovery.models.device import Device, DeviceStatus
from netpulse.discovery.models.discovery import DiscoveryResult, DiscoveryMethod


@pytest.fixture(autouse=True)
def clean_database():
    """Wipes test database history records before and after each integration test."""
    db_service.clear_history()
    yield
    db_service.clear_history()


def test_api_get_scans_empty():
    """Verify history endpoint returns empty list when no scans exist."""
    client = TestClient(app)
    response = client.get("/api/v1/scans")
    assert response.status_code == 200
    assert response.json() == []


def test_api_get_scan_by_id_not_found():
    """Verify HTTP 404 for scan searches that do not exist."""
    client = TestClient(app)
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/scans/{fake_id}")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "ScanNotFound"


def test_api_discover_drift_flow():
    """Verify end-to-end drift discovery triggers scans and reports drift analysis."""
    client = TestClient(app)
    
    # 1. Run First Sweep -> returns DriftResult with all joined (mocked)
    payload = {
        "target_network": "192.168.1.0/24",
        "methods": ["icmp"],
        "timeout_ms": 1000
    }
    
    response1 = client.post("/api/v1/discover/drift", json=payload)
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["network"] == "192.168.1.0/24"
    assert data1["old_scan_id"] is None
    assert len(data1["joined"]) > 0

    # 2. Query history -> should show 1 saved scan
    history_resp = client.get("/api/v1/scans")
    assert history_resp.status_code == 200
    assert len(history_resp.json()) == 1
    first_scan_id = history_resp.json()[0]["id"]

    # 3. Run Second Sweep -> Baseline exists now, drift should run
    response2 = client.post("/api/v1/discover/drift", json=payload)
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["old_scan_id"] == first_scan_id
    assert len(data2["unchanged"]) > 0


def test_api_scans_compare_success():
    """Verify manual comparison of two saved scans."""
    client = TestClient(app)

    # Prepare and save scan 1
    scan_id1 = uuid.uuid4()
    started = "2026-05-23T12:00:00Z"
    result1 = DiscoveryResult(
        id=scan_id1,
        network="192.168.1.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        devices=[
            Device(ip="192.168.1.5", mac="00:11:22:33:44:55", status=DeviceStatus.UP)
        ],
        started_at=started,
        finished_at=started,
        stats={}
    )
    db_service.save_scan(result1)

    # Prepare and save scan 2 (Device went offline)
    scan_id2 = uuid.uuid4()
    result2 = DiscoveryResult(
        id=scan_id2,
        network="192.168.1.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        devices=[],
        started_at=started,
        finished_at=started,
        stats={}
    )
    db_service.save_scan(result2)

    # Compare
    payload = {
        "scan_id_old": str(scan_id1),
        "scan_id_new": str(scan_id2)
    }
    response = client.post("/api/v1/scans/compare", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["old_scan_id"] == str(scan_id1)
    assert data["new_scan_id"] == str(scan_id2)
    # Check that device left
    assert len(data["left"]) == 1
    assert data["left"][0]["ip"] == "192.168.1.5"
