import pytest
import uuid
from datetime import datetime, timezone
from typer.testing import CliRunner

from netpulse_cli.main import app, db_service
from netpulse.core.models.device import Device, DeviceStatus
from netpulse.core.models.discovery import DiscoveryResult, DiscoveryMethod

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_database():
    """Wipes test database history records before and after each integration test."""
    db_service.clear_history()
    yield
    db_service.clear_history()


def test_cli_discover_history_empty():
    """Verify history command handles empty states with an informative panel."""
    result = runner.invoke(app, ["discover-history"])
    
    assert result.exit_code == 0
    assert "No History" in result.stdout or "No historic scans" in result.stdout


def test_cli_discover_history_populated():
    """Verify history command prints a structured, colored data table."""
    # Insert dummy scan
    scan_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    db_service.save_scan(DiscoveryResult(
        id=scan_id,
        network="192.168.1.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        devices=[],
        started_at=now,
        finished_at=now,
        stats={}
    ))

    result = runner.invoke(app, ["discover-history"])
    
    assert result.exit_code == 0
    assert "Discovery Scans History" in result.stdout
    assert "192.168" in result.stdout


def test_cli_discover_drift_execution():
    """Verify drift command triggers discovery sweeps and performs drift comparisons."""
    # Running it once creates the first scan baseline (all active cataloged as joined)
    result1 = runner.invoke(app, ["discover-drift", "192.168.1.0/24", "-t", "100"])
    assert result1.exit_code == 0
    assert "Drift Analysis Summary" in result1.stdout
    assert "Devices Joined" in result1.stdout

    # Running it twice compares against the newly created baseline (unchanged count rises)
    result2 = runner.invoke(app, ["discover-drift", "192.168.1.0/24", "-t", "100"])
    assert result2.exit_code == 0
    assert "Drift Analysis Summary" in result2.stdout
    assert "remained unchanged" in result2.stdout or "stable" in result2.stdout


def test_cli_discover_compare_success():
    """Verify compare command successfully formats and prints differences of saved scans."""
    # Save scan 1
    scan_id1 = uuid.uuid4()
    now = datetime.now(timezone.utc)
    db_service.save_scan(DiscoveryResult(
        id=scan_id1,
        network="192.168.1.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        devices=[
            Device(ip="192.168.1.50", mac="00:11:22:33:44:55", status=DeviceStatus.UP)
        ],
        started_at=now,
        finished_at=now,
        stats={}
    ))

    # Save scan 2 (Device went offline)
    scan_id2 = uuid.uuid4()
    db_service.save_scan(DiscoveryResult(
        id=scan_id2,
        network="192.168.1.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        devices=[],
        started_at=now,
        finished_at=now,
        stats={}
    ))

    result = runner.invoke(app, ["discover-compare", str(scan_id1), str(scan_id2)])
    assert result.exit_code == 0
    assert "Drift Analysis Summary" in result.stdout
    # Check left table rendered
    assert "Devices Left" in result.stdout
    assert "192.168.1.50" in result.stdout
