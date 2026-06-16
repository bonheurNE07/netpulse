import os
import sys
import pytest

from netpulse.discovery.engine import scan_arp, scan_icmp


def test_scan_arp_fallback():
    """Verify that scan_arp returns a list of dictionaries with correct keys."""
    # If we are in mock mode (which we are in tests without sudo/root or explicitly via NETPULSE_MOCK=1)
    results = scan_arp("172.19.57.0/24")
    assert isinstance(results, list)
    
    for device in results:
        assert isinstance(device, dict)
        assert "ip" in device
        assert "mac" in device
        assert "rtt_ms" in device
        assert "status" in device
        assert device["status"] == "up"


def test_scan_icmp_fallback():
    """Verify that scan_icmp returns a list of dictionaries with correct keys."""
    results = scan_icmp("172.19.57.0/24")
    assert isinstance(results, list)
    
    for device in results:
        assert isinstance(device, dict)
        assert "ip" in device
        assert "mac" in device  # ICMP returns None for MAC, but the key should be present
        assert "rtt_ms" in device
        assert "status" in device
        assert device["status"] == "up"
