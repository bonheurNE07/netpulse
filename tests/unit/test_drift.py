import pytest
import uuid
from datetime import datetime, timezone

from netpulse_core.models.device import Device, DeviceStatus
from netpulse_core.models.discovery import DiscoveryResult, DiscoveryMethod
from netpulse_core.services.drift import DriftService


def test_calculate_drift_first_scan():
    """Verify first scan comparison behaves cleanly (all active devices cataloged as joined)."""
    new_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    
    device = Device(
        ip="192.168.1.100",
        mac="AA:BB:CC:DD:EE:01",
        status=DeviceStatus.UP
    )

    new_scan = DiscoveryResult(
        id=new_id,
        network="192.168.1.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        devices=[device],
        started_at=now,
        finished_at=now,
        stats={}
    )

    service = DriftService()
    result = service.calculate_drift(new_scan, old_scan=None)

    assert result.network == "192.168.1.0/24"
    assert result.old_scan_id is None
    assert result.new_scan_id == new_id
    assert len(result.joined) == 1
    assert result.joined[0].ip == device.ip
    assert not result.left
    assert not result.modified
    assert not result.unchanged


def test_calculate_drift_comparative():
    """Verify full comparative analysis, isolating joined, left, modified, and unchanged hosts."""
    old_id = uuid.uuid4()
    new_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 1. Baseline Scan Devices
    # Unchanged
    dev_unchanged = Device(ip="192.168.1.5", mac="00:11:22:33:44:55", status=DeviceStatus.UP)
    # Will go offline (Left)
    dev_left = Device(ip="192.168.1.10", mac="00:11:22:33:44:aa", status=DeviceStatus.UP)
    # Will be modified
    dev_mod_old = Device(ip="192.168.1.15", mac="00:11:22:33:44:bb", status=DeviceStatus.UP, rtt_ms=1.5)

    old_scan = DiscoveryResult(
        id=old_id,
        network="192.168.1.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        devices=[dev_unchanged, dev_left, dev_mod_old],
        started_at=now,
        finished_at=now,
        stats={}
    )

    # 2. Current Scan Devices
    # Unchanged
    dev_unchanged_new = Device(ip="192.168.1.5", mac="00:11:22:33:44:55", status=DeviceStatus.UP)
    # New device (Joined)
    dev_joined = Device(ip="192.168.1.20", mac="00:11:22:33:44:cc", status=DeviceStatus.UP)
    # Modified (New MAC address reassignment)
    dev_mod_new = Device(ip="192.168.1.15", mac="FF:FF:FF:FF:FF:FF", status=DeviceStatus.UP, rtt_ms=0.99)

    new_scan = DiscoveryResult(
        id=new_id,
        network="192.168.1.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        devices=[dev_unchanged_new, dev_joined, dev_mod_new],
        started_at=now,
        finished_at=now,
        stats={}
    )

    service = DriftService()
    result = service.calculate_drift(new_scan, old_scan)

    # Assertions
    assert result.network == "192.168.1.0/24"
    assert result.old_scan_id == old_id
    assert result.new_scan_id == new_id

    # 1 Joined
    assert len(result.joined) == 1
    assert str(result.joined[0].ip) == "192.168.1.20"

    # 1 Left
    assert len(result.left) == 1
    assert str(result.left[0].ip) == "192.168.1.10"

    # 1 Modified
    assert len(result.modified) == 1
    mod = result.modified[0]
    assert mod.ip == "192.168.1.15"
    assert mod.mac_old == "00:11:22:33:44:bb"
    assert mod.mac_new == "FF:FF:FF:FF:FF:FF"

    # 1 Unchanged
    assert len(result.unchanged) == 1
    assert str(result.unchanged[0].ip) == "192.168.1.5"
