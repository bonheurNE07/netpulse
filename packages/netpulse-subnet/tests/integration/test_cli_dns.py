import pytest
import os
from typer.testing import CliRunner
from netpulse.subnet.cli import app

runner = CliRunner()

def test_cli_export_dns_bind():
    result = runner.invoke(app, ["export-dns", "10.0.0.0/24", "--format", "bind"])
    assert result.exit_code == 0
    assert "$ORIGIN 0.0.10.in-addr.arpa." in result.stdout
    assert "$GENERATE 1-254" in result.stdout
    
def test_cli_export_dns_json():
    result = runner.invoke(app, ["export-dns", "192.168.1.0/29", "--format", "json"])
    assert result.exit_code == 0
    assert '"ip": "192.168.1.1"' in result.stdout

def test_cli_export_dns_out_file(tmp_path):
    out_file = tmp_path / "export.zone"
    result = runner.invoke(app, ["export-dns", "10.0.0.0/24", "--format", "csv", "--out", str(out_file)])
    assert result.exit_code == 0
    assert "Successfully wrote DNS export" in result.stdout
    assert os.path.exists(out_file)
    with open(out_file, "r") as f:
        content = f.read()
        assert "IP Address,Record Type,Target" in content
