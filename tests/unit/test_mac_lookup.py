import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
import urllib.error

from netpulse_core.services.mac_lookup import (
    MacLookupService,
    normalize_mac,
    COMMON_OUIS
)

def test_normalize_mac():
    """Verify MAC addresses are correctly cleaned and normalized to uppercase hex."""
    assert normalize_mac("00:11:22:33:44:55") == "001122334455"
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "AABBCCDDEEFF"
    assert normalize_mac("1122.3344.5566") == "112233445566"
    assert normalize_mac("") == ""
    assert normalize_mac(None) == ""


def test_resolve_vendor_local_cache():
    """Verify that common enterprise OUIs resolve correctly from the offline dictionary."""
    # Cisco OUI prefix
    assert MacLookupService.resolve_vendor("00:00:0c:11:22:33") == "Cisco Systems"
    # Apple OUI prefix
    assert MacLookupService.resolve_vendor("3C:07:54:aa:bb:cc") == "Apple, Inc."
    # Microsoft
    assert MacLookupService.resolve_vendor("00-15-5D-11-22-33") == "Microsoft Corporation"


@patch("urllib.request.urlopen")
def test_resolve_vendor_online_fallback(mock_urlopen):
    """Verify online API lookup fallback works on unrecognized OUIs."""
    # Reset service session cache
    MacLookupService._cache = {}

    # Mock response object
    mock_response = MagicMock()
    mock_response.read.return_value = b"Ubiquiti Networks"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    # Unrecognized OUI
    vendor = MacLookupService.resolve_vendor("00:90:4B:C1:23:45")
    assert vendor == "Ubiquiti Networks"
    
    # Assert cache is populated
    assert MacLookupService._cache["00904B"] == "Ubiquiti Networks"


@patch("urllib.request.urlopen")
def test_resolve_vendor_online_not_found(mock_urlopen):
    """Verify that a 404 API response caches as 'Unknown' and does not crash."""
    MacLookupService._cache = {}

    # Mock a HTTP 404 Error
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "https://api.macvendors.com/009999", 404, "Not Found", {}, None
    )

    vendor = MacLookupService.resolve_vendor("00:99:99:11:22:33")
    assert vendor == "Unknown"
    assert MacLookupService._cache["009999"] == "Unknown"


@patch("urllib.request.urlopen")
def test_resolve_vendor_online_timeout(mock_urlopen):
    """Verify that connection timeouts gracefully return None without crashing."""
    MacLookupService._cache = {}

    # Mock timeout exception
    mock_urlopen.side_effect = TimeoutError("Request timed out")

    vendor = MacLookupService.resolve_vendor("00:88:88:11:22:33")
    assert vendor is None
    # Verify it is not cached on failures
    assert "008888" not in MacLookupService._cache


def test_parse_system_arp_table():
    """Verify that the parser correctly extracts IP-to-MAC mappings from standard Linux ARP files."""
    mock_arp_content = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.1      0x1         0x2         00:11:22:33:44:55     *        eth0
192.168.1.20     0x1         0x2         aa:bb:cc:dd:ee:ff     *        eth0
192.168.1.30     0x1         0x0         00:00:00:00:00:00     *        eth0
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp_file:
        tmp_file.write(mock_arp_content)
        tmp_path = tmp_file.name

    try:
        mappings = MacLookupService.parse_system_arp_table(tmp_path)
        assert len(mappings) == 2
        assert mappings["192.168.1.1"] == "00:11:22:33:44:55"
        assert mappings["192.168.1.20"] == "aa:bb:cc:dd:ee:ff"
        # 00:00:00:00:00:00 should be filtered out
        assert "192.168.1.30" not in mappings
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_parse_system_arp_table_missing_file():
    """Verify that parse_system_arp_table returns an empty dict if the file is missing (e.g. non-Linux)."""
    mappings = MacLookupService.parse_system_arp_table("/nonexistent/file/path")
    assert mappings == {}
