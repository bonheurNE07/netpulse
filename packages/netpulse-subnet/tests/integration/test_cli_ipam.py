import pytest
import os
from typer.testing import CliRunner
from netpulse.subnet.cli import app

runner = CliRunner()
TEST_DB = "/tmp/test_cli_ipam.db"

@pytest.fixture(autouse=True)
def setup_teardown():
    os.environ["NETPULSE_IPAM_DB"] = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_cli_ipam_init():
    result = runner.invoke(app, ["ipam", "init"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "initialized successfully" in result.stdout
    assert os.path.exists(TEST_DB)

def test_cli_vlsm_commit():
    runner.invoke(app, ["ipam", "init"], env={"COLUMNS": "200"})
    # Commit VLSM
    result = runner.invoke(app, ["vlsm", "10.0.0.0/24", "--req", "HR=100", "--commit"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "Committed 1 VLSM blocks" in result.stdout
    
    # List
    list_res = runner.invoke(app, ["ipam", "list"], env={"COLUMNS": "200"})
    assert list_res.exit_code == 0
    assert "10.0.0.0/25" in list_res.stdout
    assert "HR" in list_res.stdout
    
    # Do another VLSM, should avoid 10.0.0.0/25
    result2 = runner.invoke(app, ["vlsm", "10.0.0.0/24", "--req", "Dev=50", "--commit"], env={"COLUMNS": "200"})
    assert result2.exit_code == 0
    assert "10.0.0.128/26" in result2.stdout

def test_cli_ipam_free():
    runner.invoke(app, ["ipam", "init"], env={"COLUMNS": "200"})
    runner.invoke(app, ["split", "192.168.1.0/24", "--subnets", "4", "--commit"], env={"COLUMNS": "200"})
    # Will allocate 192.168.1.0/26, 192.168.1.64/26, 192.168.1.128/26, 192.168.1.192/26
    
    free_res = runner.invoke(app, ["ipam", "free", "192.168.1.0/23"], env={"COLUMNS": "200"})
    assert free_res.exit_code == 0
    assert "192.168.0.0/24" in free_res.stdout
    assert "192.168.1.0/24" not in free_res.stdout
