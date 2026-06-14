import ipaddress
import math
from typing import List, Dict, Optional, Any

from netpulse.subnet.models.subnet import (
    SubnetInfo,
    VLSMRequirement,
    VLSMAllocation,
    VLSMResult
)


def calculate_subnet_info(ip: str, mask_or_prefix: str) -> SubnetInfo:
    """
    Given an IP and netmask/prefix length, calculates all subnet parameters
    including wildcard, broadcast, usable host ranges, and binary representations.
    """
    prefix_or_mask = mask_or_prefix.strip().lstrip("/")
    try:
        if "." in prefix_or_mask:
            # Subnet mask format
            network = ipaddress.ip_network(f"{ip}/{prefix_or_mask}", strict=False)
        else:
            # Prefix length format
            prefix = int(prefix_or_mask)
            network = ipaddress.ip_network(f"{ip}/{prefix}", strict=False)
    except Exception as e:
        raise ValueError(f"Invalid subnet mask or prefix length '{mask_or_prefix}': {e}")

    ip_addr = ipaddress.ip_address(ip)
    netmask = network.netmask
    wildcard = network.hostmask
    broadcast = network.broadcast_address
    network_addr = network.network_address
    prefix_len = network.prefixlen

    # Usable IP calculations
    num_addresses = network.num_addresses
    if network.version == 4:
        if prefix_len == 32:
            first_usable = network_addr
            last_usable = network_addr
            total_hosts = 1
        elif prefix_len == 31:
            first_usable = network_addr
            last_usable = broadcast
            total_hosts = 2
        else:
            first_usable = network_addr + 1
            last_usable = broadcast - 1
            total_hosts = num_addresses - 2
    else:
        # IPv6
        first_usable = network_addr
        last_usable = broadcast
        total_hosts = num_addresses

    # Helper for formatting dotted binary IP strings
    def to_binary(addr: ipaddress.ip_address) -> str:
        if addr.version == 4:
            return ".".join(f"{b:08b}" for b in addr.packed)
        else:
            return ":".join(f"{int.from_bytes(addr.packed[i:i+2], 'big'):016b}" for i in range(0, 16, 2))

    binary_rep = {
        "ip": to_binary(ip_addr),
        "netmask": to_binary(netmask),
        "network": to_binary(network_addr)
    }

    return SubnetInfo(
        ip=ip_addr,
        network_cidr=str(network),
        network_address=network_addr,
        prefix_length=prefix_len,
        netmask=netmask,
        wildcard_mask=wildcard,
        broadcast_address=broadcast,
        first_usable=first_usable,
        last_usable=last_usable,
        total_hosts=total_hosts,
        binary_representation=binary_rep
    )


def split_fixed_length(
    parent_network: str,
    subnets_count: Optional[int] = None,
    hosts_per_subnet: Optional[int] = None
) -> List[str]:
    """
    Splits a parent CIDR into equal-sized subnets based either on subnets_count
    or hosts_per_subnet requirements.
    """
    try:
        network = ipaddress.ip_network(parent_network, strict=False)
    except ValueError as e:
        raise ValueError(f"Invalid parent CIDR '{parent_network}': {e}")

    max_bits = 32 if network.version == 4 else 128

    if subnets_count is not None:
        if subnets_count <= 0:
            raise ValueError("Subnets count must be greater than zero.")
        bits_to_add = math.ceil(math.log2(subnets_count))
        new_prefix = network.prefixlen + bits_to_add
        if new_prefix > max_bits:
            raise ValueError(
                f"Cannot split network {parent_network} into {subnets_count} subnets (prefix length exceeds {max_bits})."
            )
        
        subnets = list(network.subnets(new_prefix=new_prefix))
        return [str(s) for s in subnets[:subnets_count]]

    elif hosts_per_subnet is not None:
        if hosts_per_subnet <= 0:
            raise ValueError("Hosts per subnet must be greater than zero.")
        
        # Add 2 for network & broadcast overhead in IPv4 standard subnetting
        needed_hosts = hosts_per_subnet + 2 if network.version == 4 else hosts_per_subnet
        host_bits = math.ceil(math.log2(needed_hosts))
        new_prefix = max_bits - host_bits
        
        if new_prefix < network.prefixlen:
            raise ValueError(
                f"Parent network {parent_network} is too small to accommodate subnets with {hosts_per_subnet} hosts."
            )
        
        subnets = list(network.subnets(new_prefix=new_prefix))
        return [str(s) for s in subnets]
    else:
        raise ValueError("Either subnets_count or hosts_per_subnet must be provided.")


def allocate_vlsm(parent_network: str, requirements: List[Dict[str, Any]]) -> VLSMResult:
    """
    Performs Variable-Length Subnet Masking (VLSM) allocation.
    Sorts host requirements descending, and allocates the smallest power-of-two blocks possible.
    """
    try:
        parent_net = ipaddress.ip_network(parent_network, strict=False)
    except ValueError as e:
        raise ValueError(f"Invalid parent network CIDR '{parent_network}': {e}")

    if parent_net.version != 4:
        raise ValueError("VLSM allocation is only supported for IPv4 networks.")

    # 1. Parse and validate requirements
    parsed_reqs: List[VLSMRequirement] = []
    for r in requirements:
        try:
            req = VLSMRequirement(name=str(r.get("name", "Unnamed")), hosts=int(r.get("hosts", 0)))
            parsed_reqs.append(req)
        except Exception as e:
            raise ValueError(f"Invalid host requirement item {r}: {e}")

    # Sort requirements by host size in descending order
    sorted_reqs = sorted(parsed_reqs, key=lambda x: x.hosts, reverse=True)

    # Maintain pool of free subnets, sorted by network address
    free_pool: List[ipaddress.IPv4Network] = [parent_net]
    allocations: List[VLSMAllocation] = []
    unallocated: List[VLSMRequirement] = []

    for req in sorted_reqs:
        # Calculate needed size: requested hosts + 2 overhead (network and broadcast)
        needed = req.hosts + 2
        # Determine prefix length required (e.g. 32 - ceil(log2(needed)))
        prefix_needed = 32 - math.ceil(math.log2(needed))
        if prefix_needed > 32:
            prefix_needed = 32

        # Find the first fitting block in the pool
        assigned_block: Optional[ipaddress.IPv4Network] = None
        for block in free_pool:
            if block.prefixlen <= prefix_needed:
                assigned_block = block
                break

        if not assigned_block:
            # Exhausted address space for this request
            unallocated.append(req)
            continue

        # Remove chosen block from the pool
        free_pool.remove(assigned_block)

        # Split block iteratively until prefix length matches prefix_needed
        current_block = assigned_block
        while current_block.prefixlen < prefix_needed:
            # Split block into two halves of prefixlen + 1
            halves = list(current_block.subnets(new_prefix=current_block.prefixlen + 1))
            current_block = halves[0]
            # Put the second half back into the pool
            free_pool.append(halves[1])
            # Re-sort free pool by network address to ensure contiguous block grouping
            free_pool.sort(key=lambda x: x.network_address)

        # Allocate details
        total_hosts = current_block.num_addresses - 2
        if current_block.prefixlen == 32:
            total_hosts = 1
            first_usable = current_block.network_address
            last_usable = current_block.network_address
        elif current_block.prefixlen == 31:
            total_hosts = 2
            first_usable = current_block.network_address
            last_usable = current_block.broadcast_address
        else:
            first_usable = current_block.network_address + 1
            last_usable = current_block.broadcast_address - 1

        wastage = ((total_hosts - req.hosts) / total_hosts) * 100.0 if total_hosts > 0 else 0.0

        allocation = VLSMAllocation(
            name=req.name,
            hosts_requested=req.hosts,
            hosts_allocated=total_hosts,
            network_cidr=str(current_block),
            netmask=str(current_block.netmask),
            broadcast=str(current_block.broadcast_address),
            first_usable=str(first_usable),
            last_usable=str(last_usable),
            wastage_percent=round(wastage, 2)
        )
        allocations.append(allocation)

    # Format free space remaining CIDRs
    free_pool.sort(key=lambda x: x.network_address)
    free_space = [str(b) for b in free_pool]

    return VLSMResult(
        parent_network=str(parent_net),
        allocations=allocations,
        unallocated_requirements=unallocated,
        free_space_remaining=free_space
    )


def find_containing_subnet(ip: str, subnets: List[str]) -> Optional[str]:
    """
    Given an IP address and a list of subnets in CIDR notation,
    identifies which subnet contains the IP. Returns None if no subnet matches.
    """
    try:
        ip_addr = ipaddress.ip_address(ip)
    except ValueError as e:
        raise ValueError(f"Invalid IP address '{ip}': {e}")

    for subnet in subnets:
        try:
            network = ipaddress.ip_network(subnet, strict=False)
            if ip_addr in network:
                return subnet
        except ValueError:
            # Skip malformed subnet items in list
            continue

    return None
