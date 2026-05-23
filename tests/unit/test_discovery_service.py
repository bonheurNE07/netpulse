import pytest
from unittest.mock import patch
from netpulse_core.services.discovery import DiscoveryService
from netpulse_core.models.discovery import DiscoveryMethod, DiscoveryResult


@pytest.mark.asyncio
async def test_discover_network_invalid_cidr():
    """Verify that discover_network raises ValueError for malformed CIDRs."""
    service = DiscoveryService()
    
    with pytest.raises(ValueError) as exc_info:
        await service.discover_network("invalid-cidr")
    assert "Invalid network CIDR" in str(exc_info.value)


@pytest.mark.asyncio
async def test_discover_network_arp_success():
    """Verify that ARP discovery aggregates engine results correctly and resolves vendor."""
    service = DiscoveryService()
    
    mock_arp_results = [
        {"ip": "192.168.1.5", "mac": "00:11:22:33:44:55", "rtt_ms": 1.5, "status": "up"}
    ]
    
    with patch("netpulse_core.services.discovery.scan_arp") as mock_scan_arp:
        mock_scan_arp.return_value = mock_arp_results
        
        result = await service.discover_network("192.168.1.0/24", methods=[DiscoveryMethod.ARP])
        
        assert isinstance(result, DiscoveryResult)
        assert result.status == "completed"
        assert len(result.devices) == 1
        assert str(result.devices[0].ip) == "192.168.1.5"
        assert result.devices[0].mac == "00:11:22:33:44:55"
        assert result.devices[0].vendor == "Cisco Systems (Mock)"
        assert result.devices[0].rtt_ms == 1.5
        assert result.devices[0].status == "up"
        mock_scan_arp.assert_called_once_with("192.168.1.0/24", 1000, None)


@pytest.mark.asyncio
async def test_discover_network_icmp_success():
    """Verify that ICMP discovery aggregates engine results correctly."""
    service = DiscoveryService()
    
    mock_icmp_results = [
        {"ip": "192.168.1.10", "mac": None, "rtt_ms": 2.3, "status": "up"}
    ]
    
    with patch("netpulse_core.services.discovery.scan_icmp") as mock_scan_icmp:
        mock_scan_icmp.return_value = mock_icmp_results
        
        result = await service.discover_network("192.168.1.0/24", methods=[DiscoveryMethod.ICMP])
        
        assert isinstance(result, DiscoveryResult)
        assert result.status == "completed"
        assert len(result.devices) == 1
        assert str(result.devices[0].ip) == "192.168.1.10"
        assert result.devices[0].mac is None
        assert result.devices[0].vendor is None
        assert result.devices[0].rtt_ms == 2.3
        mock_scan_icmp.assert_called_once_with("192.168.1.0/24", 1000)


@pytest.mark.asyncio
async def test_discover_network_icmp_with_arp_cache_resolution():
    """Verify that ICMP sweeps resolve MAC addresses and vendors by querying the local system ARP cache."""
    service = DiscoveryService()
    
    mock_icmp_results = [
        {"ip": "192.168.1.15", "mac": None, "rtt_ms": 1.2, "status": "up"}
    ]
    
    mock_arp_mappings = {
        "192.168.1.15": "00:11:22:33:44:55"
    }
    
    with patch("netpulse_core.services.discovery.scan_icmp") as mock_scan_icmp, \
         patch("netpulse_core.services.mac_lookup.MacLookupService.parse_system_arp_table") as mock_arp:
         
        mock_scan_icmp.return_value = mock_icmp_results
        mock_arp.return_value = mock_arp_mappings
        
        result = await service.discover_network("192.168.1.0/24", methods=[DiscoveryMethod.ICMP])
        
        assert isinstance(result, DiscoveryResult)
        assert result.status == "completed"
        assert len(result.devices) == 1
        dev = result.devices[0]
        assert str(dev.ip) == "192.168.1.15"
        # Assert hardware address resolved from local system ARP table
        assert dev.mac == "00:11:22:33:44:55"
        # Assert OUI maps correctly to vendor name
        assert dev.vendor == "Cisco Systems (Mock)"
        assert dev.rtt_ms == 1.2


@pytest.mark.asyncio
async def test_discover_network_partial_failures():
    """Verify that partial failures across multiple methods are captured correctly."""
    service = DiscoveryService()
    
    mock_arp_results = [
        {"ip": "192.168.1.5", "mac": "00:11:22:33:44:55", "rtt_ms": 1.5, "status": "up"}
    ]
    
    with patch("netpulse_core.services.discovery.scan_arp") as mock_scan_arp, \
         patch("netpulse_core.services.discovery.scan_icmp") as mock_scan_icmp:
         
        mock_scan_arp.return_value = mock_arp_results
        mock_scan_icmp.side_effect = Exception("ICMP raw socket permission denied")
        
        result = await service.discover_network(
            "192.168.1.0/24", 
            methods=[DiscoveryMethod.ARP, DiscoveryMethod.ICMP]
        )
        
        assert isinstance(result, DiscoveryResult)
        assert result.status == "partial"
        assert len(result.devices) == 1
        assert len(result.errors) == 1
        assert "icmp scan failed: ICMP raw socket permission denied" in result.errors[0]
