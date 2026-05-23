import pytest
import uuid
from datetime import datetime, timezone

from netpulse_core.models.device import Device, DeviceStatus
from netpulse_core.models.discovery import DiscoveryResult, DiscoveryMethod
from netpulse_core.services.db import DatabaseService


@pytest.fixture
def db_service():
    """Initializes a temporary in-memory database connection for unit testing."""
    service = DatabaseService(db_path=":memory:")
    return service


def test_database_init(db_service):
    """Verify that tables are correctly initialized."""
    with db_service._get_connection() as conn:
        scans_count = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='scans';").fetchone()[0]
        devices_count = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='devices';").fetchone()[0]
        
    assert scans_count == 1
    assert devices_count == 1


def test_save_and_retrieve_scan(db_service):
    """Verify storing a DiscoveryResult and correctly restoring it as Pydantic models."""
    scan_id = uuid.uuid4()
    started = datetime.now(timezone.utc)
    finished = datetime.now(timezone.utc)
    
    device1 = Device(
        ip="192.168.1.5",
        mac="00:11:22:33:44:55",
        hostname="pc.local",
        status=DeviceStatus.UP,
        rtt_ms=0.45,
        vendor="Cisco"
    )
    device2 = Device(
        ip="192.168.1.10",
        mac=None,
        hostname=None,
        status=DeviceStatus.UP,
        rtt_ms=15.3,
        vendor=None
    )

    result = DiscoveryResult(
        id=scan_id,
        network="192.168.1.0/24",
        methods=[DiscoveryMethod.ARP, DiscoveryMethod.ICMP],
        status="completed",
        errors=[],
        devices=[device1, device2],
        started_at=started,
        finished_at=finished,
        stats={"scanned": 256, "responsive": 2},
        metadata={"source": "pytest"}
    )

    # Save
    db_service.save_scan(result)

    # Get by ID
    retrieved = db_service.get_scan(str(scan_id))
    
    assert retrieved is not None
    assert retrieved.id == scan_id
    assert str(retrieved.network) == "192.168.1.0/24"
    assert retrieved.status == "completed"
    assert len(retrieved.devices) == 2
    assert DiscoveryMethod.ARP in retrieved.methods
    assert DiscoveryMethod.ICMP in retrieved.methods
    
    # Assert devices restored correctly
    devs = {str(d.ip): d for d in retrieved.devices}
    assert "192.168.1.5" in devs
    assert devs["192.168.1.5"].mac == "00:11:22:33:44:55"
    assert devs["192.168.1.5"].hostname == "pc.local"
    assert devs["192.168.1.5"].vendor == "Cisco"
    assert devs["192.168.1.5"].status == DeviceStatus.UP
    assert devs["192.168.1.5"].rtt_ms == 0.45

    assert "192.168.1.10" in devs
    assert devs["192.168.1.10"].mac is None
    assert devs["192.168.1.10"].hostname is None
    assert devs["192.168.1.10"].status == DeviceStatus.UP
    assert devs["192.168.1.10"].rtt_ms == 15.3


def test_get_latest_scan(db_service):
    """Verify get_latest_scan returns the most recent completed scan for the network CIDR."""
    network = "10.0.0.0/8"
    started1 = datetime.fromisoformat("2026-05-23T12:00:00+00:00")
    started2 = datetime.fromisoformat("2026-05-23T13:00:00+00:00")

    result1 = DiscoveryResult(
        id=uuid.uuid4(),
        network=network,
        methods=[DiscoveryMethod.ICMP],
        status="completed",
        devices=[],
        started_at=started1,
        finished_at=started1,
        stats={"scanned": 16777216, "responsive": 0}
    )

    result2 = DiscoveryResult(
        id=uuid.uuid4(),
        network=network,
        methods=[DiscoveryMethod.ICMP],
        status="completed",
        devices=[],
        started_at=started2,
        finished_at=started2,
        stats={"scanned": 16777216, "responsive": 0}
    )

    # Save out of order to ensure sorting is by timestamp
    db_service.save_scan(result2)
    db_service.save_scan(result1)

    latest = db_service.get_latest_scan(network)
    assert latest is not None
    assert latest.id == result2.id


def test_get_scan_history(db_service):
    """Verify get_scan_history retrieves metadata arrays and filters correctly."""
    net1 = "192.168.1.0/24"
    net2 = "172.16.0.0/16"
    now = datetime.now(timezone.utc)

    db_service.save_scan(DiscoveryResult(
        id=uuid.uuid4(),
        network=net1,
        methods=[DiscoveryMethod.ARP],
        status="completed",
        devices=[],
        started_at=now,
        finished_at=now,
        stats={}
    ))
    db_service.save_scan(DiscoveryResult(
        id=uuid.uuid4(),
        network=net2,
        methods=[DiscoveryMethod.ICMP],
        status="completed",
        devices=[],
        started_at=now,
        finished_at=now,
        stats={}
    ))

    # All history
    history_all = db_service.get_scan_history()
    assert len(history_all) == 2

    # Filtered
    history_net1 = db_service.get_scan_history(net1)
    assert len(history_net1) == 1
    assert history_net1[0]["network"] == net1


def test_foreign_key_delete_cascade(db_service):
    """Verify that deleting a scan automatically deletes its associated devices (Cascade)."""
    scan_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    
    device = Device(
        ip="192.168.1.5",
        status=DeviceStatus.UP
    )
    result = DiscoveryResult(
        id=scan_id,
        network="192.168.1.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        devices=[device],
        started_at=now,
        finished_at=now,
        stats={}
    )

    db_service.save_scan(result)

    # Confirm saved
    with db_service._get_connection() as conn:
        devices_before = conn.execute("SELECT count(*) FROM devices WHERE scan_id = ?;", (str(scan_id),)).fetchone()[0]
        
    assert devices_before == 1

    # Delete scan
    with db_service._get_connection() as conn:
        conn.execute("DELETE FROM scans WHERE id = ?;", (str(scan_id),))
        conn.commit()

    # Confirm cascade deletion
    with db_service._get_connection() as conn:
        devices_after = conn.execute("SELECT count(*) FROM devices WHERE scan_id = ?;", (str(scan_id),)).fetchone()[0]

    assert devices_after == 0
