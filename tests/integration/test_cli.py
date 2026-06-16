import json
from unittest.mock import patch
import pytest
from typer.testing import CliRunner

from netpulse_cli.main import app
from netpulse.discovery.models.discovery import DiscoveryResult, DiscoveryMethod


runner = CliRunner()


def test_cli_version():
    """Verify that the version command prints the version string."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "NetPulse CLI version 0.1.0" in result.stdout


def test_cli_discover_invalid_cidr():
    """Verify that discover command handles malformed target networks with a clean error."""
    result = runner.invoke(app, ["discover", "999.999.999.999/24"])
    assert result.exit_code == 1
    assert "Malformed Target Range" in result.stdout or "Error:" in result.stdout


def test_cli_discover_invalid_method():
    """Verify that discover command rejects unsupported methods."""
    result = runner.invoke(app, ["discover", "172.19.57.0/24", "--method", "invalid_method"])
    assert result.exit_code == 1
    assert "Validation Error" in result.stdout or "Error:" in result.stdout


def test_cli_discover_json_format_success():
    """Verify discover command formats results as JSON when requested."""
    # We mock discover_network to return a quick mock discovery result
    mock_result = DiscoveryResult(
        network="172.19.57.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        errors=[],
        devices=[],
        started_at="2026-05-22T20:47:32.256435Z",
        finished_at="2026-05-22T20:47:32.257303Z",
        stats={"scanned": 256, "responsive": 0}
    )
    
    with patch("netpulse_cli.main.DiscoveryService.discover_network") as mock_discover:
        mock_discover.return_value = mock_result
        
        result = runner.invoke(app, ["discover", "172.19.57.0/24", "--format", "json"])
        
        assert result.exit_code == 0
        # Parse output as JSON to verify correctness
        data = json.loads(result.stdout)
        assert data["network"] == "172.19.57.0/24"
        assert data["status"] == "completed"


def test_cli_discover_table_format_success():
    """Verify discover command formats results as a table/summary by default."""
    mock_result = DiscoveryResult(
        network="172.19.57.0/24",
        methods=[DiscoveryMethod.ARP],
        status="completed",
        errors=[],
        devices=[],
        started_at="2026-05-22T20:47:32.256435Z",
        finished_at="2026-05-22T20:47:32.257303Z",
        stats={"scanned": 256, "responsive": 0}
    )
    
    with patch("netpulse_cli.main.DiscoveryService.discover_network") as mock_discover:
        mock_discover.return_value = mock_result
        
        result = runner.invoke(app, ["discover", "172.19.57.0/24"])
        
        assert result.exit_code == 0
        assert "NetPulse Scan Summary" in result.stdout
        assert "Target Network" in result.stdout


def test_cli_discover_permission_denied():
    """Verify discover command handles raw socket privilege errors by printing mitigation options."""
    mock_result = DiscoveryResult(
        network="172.19.57.0/24",
        methods=[DiscoveryMethod.ARP],
        status="failed",
        errors=["arp scan failed: Permission Denied: Failed to open raw datalink interface."],
        devices=[],
        started_at="2026-05-22T20:47:32.256435Z",
        finished_at="2026-05-22T20:47:32.257303Z",
        stats={"scanned": 256, "responsive": 0}
    )
    
    with patch("netpulse_cli.main.DiscoveryService.discover_network") as mock_discover:
        mock_discover.return_value = mock_result
        
        result = runner.invoke(app, ["discover", "172.19.57.0/24", "--method", "arp"])
        
        assert result.exit_code == 1
        assert "Privileges Required" in result.stdout
        assert "elevated privileges to open raw sockets" in result.stdout
        assert "sudo" in result.stdout
        assert "setcap" in result.stdout
