import uuid
from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from netpulse.discovery.models.device import Device, DeviceStatus
from netpulse.discovery.models.discovery import DiscoveryResult, DiscoveryMethod


def test_device_creation_defaults():
    """Verify that Device model is initialized with correct default fields."""
    device = Device(ip="192.168.1.1")
    
    assert isinstance(device.id, uuid.UUID)
    assert str(device.ip) == "192.168.1.1"
    assert device.mac is None
    assert device.hostname is None
    assert device.vendor is None
    assert device.status == DeviceStatus.UNKNOWN
    assert device.rtt_ms is None
    assert isinstance(device.created_at, datetime)
    assert isinstance(device.last_seen, datetime)
    assert device.metadata == {}


def test_device_validation_valid_mac():
    """Verify that valid MAC address formats are accepted."""
    device = Device(ip="10.0.0.1", mac="00:11:22:33:44:55")
    assert device.mac == "00:11:22:33:44:55"
    
    device_dash = Device(ip="10.0.0.1", mac="00-11-22-33-44-55")
    assert device_dash.mac == "00-11-22-33-44-55"


def test_device_validation_invalid_mac():
    """Verify that malformed MAC address formats are rejected."""
    with pytest.raises(ValidationError):
        Device(ip="10.0.0.1", mac="00:11:22:33:44")
        
    with pytest.raises(ValidationError):
        Device(ip="10.0.0.1", mac="invalid-mac-address")


def test_device_validation_invalid_ip():
    """Verify that malformed IP address formats are rejected."""
    with pytest.raises(ValidationError):
        Device(ip="999.999.999.999")


def test_discovery_result_properties():
    """Verify DiscoveryResult computed properties work as expected."""
    start = datetime.now(timezone.utc)
    finish = start + timedelta(seconds=2.5)
    
    devices = [
        Device(ip="192.168.1.1", status=DeviceStatus.UP),
        Device(ip="192.168.1.2", status=DeviceStatus.DOWN),
        Device(ip="192.168.1.3", status=DeviceStatus.UP),
        Device(ip="192.168.1.4", status=DeviceStatus.UNKNOWN),
    ]
    
    result = DiscoveryResult(
        network="192.168.1.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        devices=devices,
        started_at=start,
        finished_at=finish
    )
    
    assert result.duration_s == 2.5
    assert result.total_discovered == 2
    assert str(result.network) == "192.168.1.0/24"
    assert result.methods == [DiscoveryMethod.ARP]
