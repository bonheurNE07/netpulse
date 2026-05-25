import pytest
from unittest.mock import AsyncMock, patch
import asyncio

from netpulse_core.services.port_scanner import PortScannerService, COMMON_PORTS_MAP

@pytest.mark.asyncio
async def test_scan_single_port_open():
    """Verify that an open port is detected and the correct service mapped."""
    scanner = PortScannerService()
    
    # Mock asyncio.open_connection to succeed
    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    
    with patch("asyncio.open_connection", AsyncMock(return_value=(mock_reader, mock_writer))) as mock_open:
        res = await scanner.scan_single_port("192.168.1.1", 80, timeout_s=0.1)
        
        assert res is not None
        assert res["port"] == 80
        assert res["service"] == "HTTP"
        assert res["status"] == "open"
        mock_open.assert_called_once_with("192.168.1.1", 80)
        mock_writer.close.assert_called_once()


@pytest.mark.asyncio
async def test_scan_single_port_closed():
    """Verify that a closed port is detected as closed and returns None."""
    scanner = PortScannerService()
    
    # Mock asyncio.open_connection to raise ConnectionRefusedError
    with patch("asyncio.open_connection", AsyncMock(side_effect=ConnectionRefusedError())):
        res = await scanner.scan_single_port("192.168.1.1", 9999, timeout_s=0.1)
        
        assert res is None


@pytest.mark.asyncio
async def test_scan_single_port_timeout():
    """Verify that a connection timeout returns None."""
    scanner = PortScannerService()
    
    # Mock asyncio.wait_for to raise TimeoutError
    with patch("asyncio.open_connection", AsyncMock()):
        with patch("asyncio.wait_for", AsyncMock(side_effect=asyncio.TimeoutError())):
            res = await scanner.scan_single_port("192.168.1.1", 80, timeout_s=0.1)
            
            assert res is None


@pytest.mark.asyncio
async def test_scan_device_ports():
    """Verify that scanning multiple ports on a single device returns only open ports."""
    scanner = PortScannerService()
    
    # Mock open_connection to succeed for 22 (SSH) and fail/refuse for 80 (HTTP)
    async def mock_connect(ip, port):
        if port == 22:
            return AsyncMock(), AsyncMock()
        raise ConnectionRefusedError()

    with patch("asyncio.open_connection", side_effect=mock_connect):
        results = await scanner.scan_device_ports("192.168.1.5", [22, 80], timeout_ms=100)
        
        assert len(results) == 1
        assert results[0]["port"] == 22
        assert results[0]["service"] == "SSH"
        assert results[0]["status"] == "open"


@pytest.mark.asyncio
async def test_scan_multiple_devices_ports():
    """Verify that port scans across multiple devices correctly maps results to each device."""
    scanner = PortScannerService()
    
    # Mock open_connection to return success on 22 for both hosts, and 443 only on the second host
    async def mock_connect(ip, port):
        if port == 22:
            return AsyncMock(), AsyncMock()
        if port == 443 and ip == "192.168.1.2":
            return AsyncMock(), AsyncMock()
        raise ConnectionRefusedError()

    with patch("asyncio.open_connection", side_effect=mock_connect):
        ips = ["192.168.1.1", "192.168.1.2"]
        ports = [22, 443]
        
        results = await scanner.scan_multiple_devices_ports(ips, ports, timeout_ms=100)
        
        assert "192.168.1.1" in results
        assert "192.168.1.2" in results
        
        # 192.168.1.1 should only have port 22 open
        assert len(results["192.168.1.1"]) == 1
        assert results["192.168.1.1"][0]["port"] == 22
        
        # 192.168.1.2 should have ports 22 and 443 open
        assert len(results["192.168.1.2"]) == 2
        ports_found = [r["port"] for r in results["192.168.1.2"]]
        assert 22 in ports_found
        assert 443 in ports_found
