import pytest
from pydantic import ValidationError
from netpulse.subnet.services.subnet import (
    calculate_subnet_info,
    split_fixed_length,
    allocate_vlsm,
    find_containing_subnet
)
from netpulse.subnet.models.subnet import SubnetInfo, VLSMResult


def test_calculate_subnet_info_ipv4_standard():
    """Verify detailed calculations for standard IPv4 network configuration."""
    info = calculate_subnet_info("192.168.1.50", "24")
    
    assert isinstance(info, SubnetInfo)
    assert str(info.ip) == "192.168.1.50"
    assert info.network_cidr == "192.168.1.0/24"
    assert str(info.network_address) == "192.168.1.0"
    assert info.prefix_length == 24
    assert str(info.netmask) == "255.255.255.0"
    assert str(info.wildcard_mask) == "0.0.0.255"
    assert str(info.broadcast_address) == "192.168.1.255"
    assert str(info.first_usable) == "192.168.1.1"
    assert str(info.last_usable) == "192.168.1.254"
    assert info.total_hosts == 254
    assert "ip" in info.binary_representation
    assert "netmask" in info.binary_representation
    assert "network" in info.binary_representation


def test_calculate_subnet_info_ipv4_mask_notation():
    """Verify calculations when subnet mask is provided in dotted decimal format."""
    info = calculate_subnet_info("10.0.0.1", "255.255.0.0")
    
    assert info.network_cidr == "10.0.0.0/16"
    assert info.prefix_length == 16
    assert str(info.netmask) == "255.255.0.0"
    assert str(info.wildcard_mask) == "0.0.255.255"
    assert str(info.broadcast_address) == "10.0.255.255"
    assert str(info.first_usable) == "10.0.0.1"
    assert str(info.last_usable) == "10.0.255.254"
    assert info.total_hosts == 65534


def test_calculate_subnet_info_edge_cases():
    """Verify subnet calculations for point-to-point and host-route networks."""
    # /31 Point-to-Point
    info_31 = calculate_subnet_info("192.168.1.2", "31")
    assert info_31.total_hosts == 2
    assert str(info_31.first_usable) == "192.168.1.2"
    assert str(info_31.last_usable) == "192.168.1.3"

    # /32 Host route
    info_32 = calculate_subnet_info("192.168.1.5", "32")
    assert info_32.total_hosts == 1
    assert str(info_32.first_usable) == "192.168.1.5"
    assert str(info_32.last_usable) == "192.168.1.5"


def test_calculate_subnet_info_invalid_inputs():
    """Verify that invalid IP or mask values raise appropriate errors."""
    with pytest.raises(ValueError):
        calculate_subnet_info("192.168.1.50", "99")  # Invalid prefix
        
    with pytest.raises(ValueError):
        calculate_subnet_info("192.168.1.50", "255.255.255.999")  # Invalid mask
        
    with pytest.raises(ValueError):
        calculate_subnet_info("999.999.999.999", "24")  # Invalid IP


def test_split_fixed_length_by_count():
    """Verify partitioning a network into equal chunks by subnets count."""
    subnets = split_fixed_length("192.168.1.0/24", subnets_count=4)
    
    assert len(subnets) == 4
    assert subnets[0] == "192.168.1.0/26"
    assert subnets[1] == "192.168.1.64/26"
    assert subnets[2] == "192.168.1.128/26"
    assert subnets[3] == "192.168.1.192/26"


def test_split_fixed_length_by_hosts():
    """Verify partitioning a network based on required host capacity per subnet."""
    subnets = split_fixed_length("192.168.1.0/24", hosts_per_subnet=50)
    
    # 50 hosts + 2 overhead requires a /26 block (capacity 62 usable hosts)
    assert len(subnets) == 4
    assert all(s.endswith("/26") for s in subnets)


def test_split_fixed_length_invalid():
    """Verify that split errors out with impossible or malformed parameters."""
    with pytest.raises(ValueError):
        # Exceeds maximum bits
        split_fixed_length("192.168.1.0/24", subnets_count=512)
        
    with pytest.raises(ValueError):
        # Parent too small
        split_fixed_length("192.168.1.0/30", hosts_per_subnet=50)
        
    with pytest.raises(ValueError):
        # Invalid parent CIDR
        split_fixed_length("invalid-cidr", subnets_count=4)


def test_allocate_vlsm_success():
    """Verify optimal allocation and zero overlap for various host requirements."""
    requirements = [
        {"name": "Sales", "hosts": 20},
        {"name": "HR", "hosts": 120},
        {"name": "Dev", "hosts": 50},
        {"name": "Links", "hosts": 2}
    ]
    
    result = allocate_vlsm("192.168.1.0/24", requirements)
    
    assert isinstance(result, VLSMResult)
    assert result.parent_network == "192.168.1.0/24"
    assert len(result.allocations) == 4
    assert not result.unallocated_requirements
    
    # Sort by CIDR to check sequential non-overlapping allocations
    sorted_allocations = sorted(result.allocations, key=lambda a: a.network_cidr)
    
    # HR: 120 hosts -> needs block of size 128 (/25)
    # Dev: 50 hosts -> needs block of size 64 (/26)
    # Sales: 20 hosts -> needs block of size 32 (/27)
    # Links: 2 hosts -> needs block of size 4 (/30)
    
    # Let's inspect allocation naming and prefix sizes
    allocations_by_name = {a.name: a for a in result.allocations}
    
    assert allocations_by_name["HR"].network_cidr.endswith("/25")
    assert allocations_by_name["Dev"].network_cidr.endswith("/26")
    assert allocations_by_name["Sales"].network_cidr.endswith("/27")
    assert allocations_by_name["Links"].network_cidr.endswith("/30")


def test_allocate_vlsm_exhaustion():
    """Verify that requests exceeding address capacities are marked as unallocated."""
    requirements = [
        {"name": "SuperDepartment", "hosts": 200},
        {"name": "MediumDepartment", "hosts": 100}
    ]
    
    # 192.168.1.0/24 total capacity is 254 usable hosts.
    # SuperDepartment (200 hosts) needs a /24 block.
    # MediumDepartment (100 hosts) needs a /25 block.
    # Total space exceeds /24 block.
    
    result = allocate_vlsm("192.168.1.0/24", requirements)
    
    assert len(result.allocations) == 1
    assert result.allocations[0].name == "SuperDepartment"
    assert len(result.unallocated_requirements) == 1
    assert result.unallocated_requirements[0].name == "MediumDepartment"


def test_find_containing_subnet():
    """Verify that find_containing_subnet matches correct containing network scopes."""
    subnets = [
        "192.168.1.0/26",
        "192.168.1.64/26",
        "192.168.1.128/26"
    ]
    
    assert find_containing_subnet("192.168.1.45", subnets) == "192.168.1.0/26"
    assert find_containing_subnet("192.168.1.70", subnets) == "192.168.1.64/26"
    assert find_containing_subnet("10.0.0.1", subnets) is None


def test_find_containing_subnet_malformed_ignored():
    """Verify that malformed subnet elements in candidate list are ignored without crashing."""
    subnets = [
        "invalid-subnet-cidr",
        "192.168.1.0/26"
    ]
    assert find_containing_subnet("192.168.1.15", subnets) == "192.168.1.0/26"
