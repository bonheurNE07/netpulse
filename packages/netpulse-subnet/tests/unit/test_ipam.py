import pytest
import os
import sqlite3

# Set env var before importing ipam
TEST_DB = "/tmp/test_netpulse_ipam.db"

from netpulse.subnet.services.ipam import init_db, add_reservation, get_reservations, get_reservations_for_parent

@pytest.fixture(autouse=True)
def setup_teardown():
    os.environ["NETPULSE_IPAM_DB"] = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_init_db():
    assert os.path.exists(TEST_DB)
    conn = sqlite3.connect(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='subnets'")
    assert cursor.fetchone() is not None
    conn.close()

def test_add_and_get_reservations():
    add_reservation("10.0.0.0/24", "HR VLAN", "10.0.0.0/16")
    add_reservation("10.0.1.0/24", "Dev VLAN", "10.0.0.0/16")
    
    res = get_reservations()
    assert len(res) == 2
    assert res[0]["network"] == "10.0.0.0/24"
    assert res[0]["description"] == "HR VLAN"
    assert res[1]["network"] == "10.0.1.0/24"

def test_get_reservations_for_parent():
    add_reservation("192.168.1.0/25", "Reserved 1", "192.168.1.0/24")
    add_reservation("192.168.2.0/24", "Different Parent", "192.168.0.0/16")
    
    parent_res = get_reservations_for_parent("192.168.1.0/24")
    assert len(parent_res) == 1
    assert parent_res[0] == "192.168.1.0/25"
