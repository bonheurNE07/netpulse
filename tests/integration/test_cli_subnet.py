import pytest
from typer.testing import CliRunner
from netpulse_cli.main import app

runner = CliRunner()


def test_cli_subnet_info_success():
    """Verify subnet info command prints parameters and bitwise alignment."""
    result = runner.invoke(app, ["subnet", "info", "192.168.1.50/24"])
    
    assert result.exit_code == 0
    assert "Subnet Parameters" in result.stdout
    assert "Bitwise Binary Alignment" in result.stdout
    assert "192.168.1." in result.stdout
    assert "254" in result.stdout


def test_cli_subnet_info_invalid():
    """Verify subnet info command handles malformed masks gracefully."""
    result = runner.invoke(app, ["subnet", "info", "192.168.1.50/99"])
    
    assert result.exit_code == 1
    assert "Calculation Error" in result.stdout or "Error" in result.stdout


def test_cli_subnet_split_success():
    """Verify subnet split command renders partitions in clear table layout."""
    result = runner.invoke(app, ["subnet", "split", "192.168.1.0/24", "--subnets", "4"])
    
    assert result.exit_code == 0
    assert "Equal Partition Split" in result.stdout
    assert "192.168.1." in result.stdout


def test_cli_subnet_split_missing_options():
    """Verify split command triggers validation warning if no split criteria is given."""
    result = runner.invoke(app, ["subnet", "split", "192.168.1.0/24"])
    
    assert result.exit_code == 1
    assert "Validation Error" in result.stdout


def test_cli_subnet_vlsm_success():
    """Verify subnet vlsm command allocates spaces and displays wastage percent."""
    result = runner.invoke(app, ["subnet", "vlsm", "192.168.1.0/24", "--req", "HR=120,Dev=50"])
    
    assert result.exit_code == 0
    assert "VLSM Address Allocation" in result.stdout
    assert "HR" in result.stdout
    assert "Dev" in result.stdout
    assert "Available Unallocated Blocks" in result.stdout


def test_cli_subnet_vlsm_invalid_format():
    """Verify vlsm command handles invalid requirements formatted strings with clear errors."""
    result = runner.invoke(app, ["subnet", "vlsm", "192.168.1.0/24", "--req", "HR=invalid_host_count"])
    
    assert result.exit_code == 1
    assert "Validation Error" in result.stdout


def test_cli_subnet_discover_match():
    """Verify discover command successfully highlights containing range match."""
    result = runner.invoke(app, [
        "subnet", "discover", "192.168.1.45",
        "--subnets", "192.168.1.0/26,192.168.1.64/26"
    ])
    
    assert result.exit_code == 0
    assert "Subnet Discovered" in result.stdout
    assert "Match Discovered" in result.stdout
    assert "192.168.1." in result.stdout


def test_cli_subnet_discover_no_match():
    """Verify discover command displays lookup failure if no subnet contains the IP."""
    result = runner.invoke(app, [
        "subnet", "discover", "10.0.0.1",
        "--subnets", "192.168.1.0/26"
    ])
    
    assert result.exit_code == 1
    assert "No Match Found" in result.stdout
