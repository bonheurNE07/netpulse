import pytest
from typer.testing import CliRunner

from netpulse.discovery.cli import app

runner = CliRunner()

def test_cli_scan_valid_network():
    result = runner.invoke(app, ["scan", "127.0.0.1/32", "--timeout", "100"])
    if result.exit_code != 0 and result.exception:
        raise result.exception
    assert result.exit_code == 0
    assert "127.0.0.1" in result.stdout

def test_cli_scan_invalid_network():
    result = runner.invoke(app, ["scan", "invalid", "--timeout", "100"])
    assert result.exit_code != 0
    assert "Invalid network" in str(result.exception) or "Invalid network" in result.stdout
