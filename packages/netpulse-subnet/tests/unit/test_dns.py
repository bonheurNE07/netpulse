import pytest
from netpulse.subnet.services.dns import (
    generate_reverse_zone_name,
    export_to_bind,
    export_to_csv,
    export_to_json,
    get_ptr_records
)

def test_generate_reverse_zone_name_ipv4():
    assert generate_reverse_zone_name("192.168.1.0/24") == "1.168.192.in-addr.arpa"
    assert generate_reverse_zone_name("10.0.0.0/16") == "0.10.in-addr.arpa"
    assert generate_reverse_zone_name("172.16.0.0/16") == "16.172.in-addr.arpa"
    assert generate_reverse_zone_name("1.2.3.4/32") == "3.2.1.in-addr.arpa"

def test_generate_reverse_zone_name_ipv6():
    assert generate_reverse_zone_name("2001:db8::/32") == "8.b.d.0.1.0.0.2.ip6.arpa"
    assert generate_reverse_zone_name("2001:db8:acad::/48") == "d.a.c.a.8.b.d.0.1.0.0.2.ip6.arpa"

def test_get_ptr_records_ipv4():
    records = get_ptr_records("192.168.1.0/29", "example.com")
    assert len(records) == 6 # /29 has 6 usable hosts
    assert records[0]["ip"] == "192.168.1.1"
    assert records[0]["ptr"] == "host-192-168-1-1.example.com."
    assert records[0]["reverse_name"] == "1.1.168.192.in-addr.arpa"

def test_export_to_bind_ipv4_24():
    out = export_to_bind("10.0.5.0/24", "internal.local")
    assert "$ORIGIN 5.0.10.in-addr.arpa." in out
    assert "$GENERATE 1-254 $ IN PTR host-10-0-5-$.internal.local." in out

def test_export_to_bind_ipv4_small():
    out = export_to_bind("192.168.1.0/29", "internal.local")
    assert "$ORIGIN 1.168.192.in-addr.arpa." in out
    assert "1                              IN PTR host-192-168-1-1.internal.local." in out

def test_export_to_csv():
    out = export_to_csv("10.0.0.0/30", "test.com")
    assert "IP Address,Record Type,Target" in out
    assert "10.0.0.1,PTR,host-10-0-0-1.test.com." in out

def test_export_to_json():
    out = export_to_json("192.168.1.0/30", "test.com")
    assert '"ip": "192.168.1.1"' in out
    assert '"ptr": "host-192-168-1-1.test.com."' in out
