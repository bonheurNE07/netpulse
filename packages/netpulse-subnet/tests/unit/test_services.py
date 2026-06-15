import pytest
from netpulse.subnet.services.subnet import (
    calculate_subnet_info,
    split_fixed_length,
    allocate_vlsm,
    find_containing_subnet
)

def test_calculate_subnet_info_ipv4():
    info = calculate_subnet_info("192.168.1.50", "24")
    assert str(info.ip) == "192.168.1.50"
    assert info.network_cidr == "192.168.1.0/24"
    assert str(info.network_address) == "192.168.1.0"
    assert str(info.broadcast_address) == "192.168.1.255"
    assert str(info.netmask) == "255.255.255.0"
    assert str(info.first_usable) == "192.168.1.1"
    assert str(info.last_usable) == "192.168.1.254"
    assert info.total_hosts == 254

def test_calculate_subnet_info_ipv6():
    info = calculate_subnet_info("2001:db8::1", "64")
    assert str(info.ip) == "2001:db8::1"
    assert info.network_cidr == "2001:db8::/64"
    assert str(info.network_address) == "2001:db8::"
    assert info.broadcast_address is None
    assert str(info.first_usable) == "2001:db8::1"
    assert info.total_hosts == (2**64) - 1

def test_split_fixed_length_ipv4():
    # Split a /24 into 4 subnets
    subnets = split_fixed_length("192.168.1.0/24", subnets_count=4)
    assert len(subnets) == 4
    assert subnets[0] == "192.168.1.0/26"
    assert subnets[1] == "192.168.1.64/26"
    assert subnets[2] == "192.168.1.128/26"
    assert subnets[3] == "192.168.1.192/26"

def test_split_fixed_length_ipv6_truncation():
    # Splitting a /48 to /64s yields 65,536 subnets.
    subnets = split_fixed_length("2001:db8::/48", hosts_per_subnet=(2**64 - 2))
    assert len(subnets) <= 65536
    assert subnets[0] == "2001:db8::/64"

def test_allocate_vlsm_ipv4():
    requirements = [
        {"name": "HR", "hosts": 100},
        {"name": "IT", "hosts": 50},
        {"name": "Sales", "hosts": 25}
    ]
    result = allocate_vlsm("192.168.1.0/24", requirements)
    assert result.parent_network == "192.168.1.0/24"
    assert len(result.allocations) == 3
    
    # HR gets a /25
    hr_alloc = next(a for a in result.allocations if a.name == "HR")
    assert hr_alloc.network_cidr == "192.168.1.0/25"
    assert hr_alloc.hosts_allocated == 126
    
    # IT gets a /26
    it_alloc = next(a for a in result.allocations if a.name == "IT")
    assert it_alloc.network_cidr == "192.168.1.128/26"
    
def test_find_containing_subnet():
    subnets = ["10.0.0.0/8", "192.168.1.0/24", "2001:db8::/32"]
    
    match1 = find_containing_subnet("192.168.1.50", subnets)
    assert match1 == "192.168.1.0/24"
    
    match2 = find_containing_subnet("172.16.0.1", subnets)
    assert match2 is None
    
    match3 = find_containing_subnet("2001:db8:1234::1", subnets)
    assert match3 == "2001:db8::/32"

def test_validate_subnets_overlaps():
    from netpulse.subnet.services.subnet import validate_subnets
    # 192.168.1.128/25 is inside 192.168.1.0/24
    subnets = ["10.0.0.0/8", "192.168.1.0/24", "192.168.1.128/25"]
    result = validate_subnets(subnets)
    
    assert result.has_overlaps is True
    assert len(result.overlaps) == 1
    assert result.overlaps[0].subnet1 == "192.168.1.0/24"
    assert result.overlaps[0].subnet2 == "192.168.1.128/25"

def test_validate_subnets_free_space():
    from netpulse.subnet.services.subnet import validate_subnets
    subnets = ["192.168.1.0/24"]
    parent = "192.168.0.0/23"
    result = validate_subnets(subnets, parent_network=parent)
    
    assert result.has_overlaps is False
    assert len(result.free_space) == 1
    assert result.free_space[0] == "192.168.0.0/24"

def test_summarize_subnets_contiguous():
    from netpulse.subnet.services.subnet import summarize_subnets
    # Four /24s exactly form a /22
    subnets = ["192.168.0.0/24", "192.168.1.0/24", "192.168.2.0/24", "192.168.3.0/24"]
    result = summarize_subnets(subnets)
    assert result.supernet == "192.168.0.0/22"
    assert result.has_slack is False
    assert result.slack_ips == 0
    assert result.provided_ips == 1024

def test_summarize_subnets_discontiguous():
    from netpulse.subnet.services.subnet import summarize_subnets
    # A /24 and another /24 ten blocks away
    subnets = ["192.168.0.0/24", "192.168.10.0/24"]
    result = summarize_subnets(subnets)
    assert result.supernet == "192.168.0.0/20"
    assert result.has_slack is True
    assert result.slack_ips == 4096 - 512
    assert result.provided_ips == 512

def test_allocate_vlsm_with_reserved():
    from netpulse.subnet.services.subnet import allocate_vlsm
    reqs = [{"name": "A", "hosts": 100}]
    # 192.168.1.0/25 is reserved, so it should allocate from 192.168.1.128
    res = allocate_vlsm("192.168.1.0/24", reqs, reserved_blocks=["192.168.1.0/25"])
    assert len(res.allocations) == 1
    assert res.allocations[0].network_cidr == "192.168.1.128/25"

def test_split_fixed_length_with_reserved():
    from netpulse.subnet.services.subnet import split_fixed_length
    # Split /24 into 4 subnets (/26s), but reserve the first one
    res = split_fixed_length("10.0.0.0/24", subnets_count=4, reserved_blocks=["10.0.0.0/26"])
    assert len(res) == 3
    assert "10.0.0.0/26" not in res
    assert "10.0.0.64/26" in res
