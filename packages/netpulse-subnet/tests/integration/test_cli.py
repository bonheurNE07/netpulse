import pytest
from typer.testing import CliRunner
from netpulse.subnet.cli import app

runner = CliRunner()

def test_cli_info_ipv4():
    result = runner.invoke(app, ["info", "192.168.1.50/24"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "192.168.1.0/24" in result.stdout
    assert "192.168.1.255" in result.stdout

def test_cli_info_ipv6():
    result = runner.invoke(app, ["info", "2001:db8::1/64"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "2001:db8::/64" in result.stdout
    assert "N/A (IPv6)" in result.stdout

def test_cli_split_ipv4():
    result = runner.invoke(app, ["split", "10.0.0.0/8", "--subnets", "4"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "10.0.0.0/10" in result.stdout
    assert "10.64.0.0/10" in result.stdout

def test_cli_vlsm():
    result = runner.invoke(app, ["vlsm", "192.168.1.0/24", "--req", "HR=100"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "192.168.1.0/25" in result.stdout
    assert "HR" in result.stdout

def test_cli_discover():
    result = runner.invoke(app, ["discover", "192.168.1.50", "--subnets", "192.168.1.0/26,192.168.1.64/26"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "Match Discovered!" in result.stdout
    assert "192.168.1.0/26" in result.stdout

def test_cli_validate():
    result = runner.invoke(app, ["validate", "192.168.1.0/24", "192.168.1.128/25", "--parent", "192.168.1.0/23"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "CONFLICTS DETECTED" in result.stdout
    assert "192.168.1.0/24" in result.stdout
    assert "192.168.1.128/25" in result.stdout
    assert "Available Unallocated Blocks" in result.stdout
    assert "192.168.0.0/24" in result.stdout

def test_cli_summarize():
    result = runner.invoke(app, ["summarize", "192.168.0.0/24", "192.168.1.0/24", "192.168.2.0/24", "192.168.3.0/24"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "Route Summarization Result" in result.stdout
    assert "192.168.0.0/22" in result.stdout
    assert "Slack Warning" not in result.stdout

def test_cli_summarize_slack():
    result = runner.invoke(app, ["summarize", "192.168.0.0/24", "192.168.10.0/24"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "Route Summarization Result" in result.stdout
    assert "192.168.0.0/20" in result.stdout
    assert "Slack Warning" in result.stdout
