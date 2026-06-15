import ipaddress
import math
from typing import List, Dict, Optional, Any

from netpulse.subnet.models.subnet import (
    SubnetInfo,
    VLSMRequirement,
    VLSMAllocation,
    VLSMResult,
    ValidationResult,
    OverlapPair
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
    network_addr = network.network_address
    prefix_len = network.prefixlen

    # Usable IP calculations
    num_addresses = network.num_addresses
    if network.version == 4:
        broadcast = network.broadcast_address
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
        # IPv6 natively has no broadcast address
        broadcast = None
        if prefix_len == 128:
            first_usable = network_addr
            last_usable = network_addr
            total_hosts = 1
        elif prefix_len == 127:
            first_usable = network_addr
            last_usable = network_addr + 1
            total_hosts = 2
        else:
            first_usable = network_addr + 1
            last_usable = network_addr + num_addresses - 1
            total_hosts = num_addresses - 1  # Excluding the subnet-router anycast (network_addr)

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
    subnets_count: int = None,
    hosts_per_subnet: int = None,
    reserved_blocks: List[str] = None
) -> List[str]:
    """
    Splits a parent CIDR into equal-sized subnets based either on subnets_count
    or hosts_per_subnet requirements.
    Safely limits output to 65536 subnets to prevent MemoryErrors on IPv6.
    """
    try:
        parent_net = ipaddress.ip_network(parent_network, strict=False)
    except ValueError as e:
        raise ValueError(f"Invalid parent CIDR '{parent_network}': {e}")

    MAX_SUBNETS = 65536

    if subnets_count is not None:
        if subnets_count <= 0 or not (subnets_count & (subnets_count - 1) == 0):
            raise ValueError("subnets_count must be a positive power of 2.")
            
        new_prefix = parent_net.prefixlen + int(math.log2(subnets_count))
        if new_prefix > parent_net.max_prefixlen:
            raise ValueError(f"Cannot split /{parent_net.prefixlen} into {subnets_count} subnets (prefix too long).")
            
        subnets = list(parent_net.subnets(new_prefix=new_prefix))
        
        # Exclude reserved blocks if any
        if reserved_blocks:
            valid_subnets = []
            for s in subnets:
                is_free = True
                for r in reserved_blocks:
                    try:
                        r_net = ipaddress.ip_network(r, strict=False)
                        if s.overlaps(r_net):
                            is_free = False
                            break
                    except ValueError:
                        continue
                if is_free:
                    valid_subnets.append(s)
            subnets = valid_subnets
            
        return [str(s) for s in subnets[:MAX_SUBNETS]]

    elif hosts_per_subnet is not None:
        if hosts_per_subnet <= 0:
            raise ValueError("hosts_per_subnet must be a positive integer.")
            
        needed_addresses = hosts_per_subnet + 2 if parent_net.version == 4 else hosts_per_subnet + 1
        host_bits = math.ceil(math.log2(needed_addresses))
        new_prefix = parent_net.max_prefixlen - host_bits
        
        if new_prefix < parent_net.prefixlen:
            raise ValueError(f"Parent network /{parent_net.prefixlen} is too small to fit subnets with {hosts_per_subnet} hosts.")
            
        subnets = list(parent_net.subnets(new_prefix=new_prefix))
        
        if reserved_blocks:
            valid_subnets = []
            for s in subnets:
                is_free = True
                for r in reserved_blocks:
                    try:
                        r_net = ipaddress.ip_network(r, strict=False)
                        if s.overlaps(r_net):
                            is_free = False
                            break
                    except ValueError:
                        continue
                if is_free:
                    valid_subnets.append(s)
            subnets = valid_subnets
            
        return [str(s) for s in subnets[:MAX_SUBNETS]]
    else:
        raise ValueError("Either subnets_count or hosts_per_subnet must be provided.")


def allocate_vlsm(parent_network: str, requirements: List[Dict[str, Any]], reserved_blocks: List[str] = None) -> VLSMResult:
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
    
    if reserved_blocks:
        for r in reserved_blocks:
            try:
                r_net = ipaddress.ip_network(r, strict=False)
                new_pool = []
                for free_block in free_pool:
                    if r_net.subnet_of(free_block):
                        new_pool.extend(list(free_block.address_exclude(r_net)))
                    elif not free_block.overlaps(r_net):
                        new_pool.append(free_block)
                free_pool = new_pool
            except ValueError:
                continue
        free_pool.sort(key=lambda x: x.network_address)
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

def validate_subnets(subnets: List[str], parent_network: Optional[str] = None) -> ValidationResult:
    """
    Ingests a list of subnets and detects any mathematical overlaps using an O(N log N) sweep line algorithm.
    If a parent network is provided, calculates the remaining free space using address exclusion.
    """
    parsed_networks = []
    for s in subnets:
        if not s.strip():
            continue
        try:
            net = ipaddress.ip_network(s.strip(), strict=False)
            parsed_networks.append(net)
        except ValueError:
            raise ValueError(f"Invalid subnet provided for validation: '{s}'")
            
    # Sweep line algorithm for overlap detection
    # Sort networks by their integer base address
    parsed_networks.sort(key=lambda n: int(n.network_address))
    
    overlaps: List[OverlapPair] = []
    
    # Iterate and check if current network overlaps with previous max extent
    if parsed_networks:
        current_max_net = parsed_networks[0]
        
        for i in range(1, len(parsed_networks)):
            net = parsed_networks[i]
            
            def get_broadcast(n):
                if n.version == 4:
                    return int(n.broadcast_address)
                else:
                    return int(n.network_address) + n.num_addresses - 1
            
            if int(net.network_address) <= get_broadcast(current_max_net):
                overlaps.append(OverlapPair(
                    subnet1=str(current_max_net),
                    subnet2=str(net)
                ))
                if get_broadcast(net) > get_broadcast(current_max_net):
                    current_max_net = net
            else:
                current_max_net = net

    # Free Space Calculation
    free_space_cidrs = []
    if parent_network:
        try:
            parent_net = ipaddress.ip_network(parent_network.strip(), strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid parent network '{parent_network}': {e}")
            
        valid_subnets_in_parent = []
        for n in parsed_networks:
            if n.subnet_of(parent_net):
                valid_subnets_in_parent.append(n)
                
        if valid_subnets_in_parent:
            collapsed = list(ipaddress.collapse_addresses(valid_subnets_in_parent))
            free_pool = [parent_net]
            
            for used_block in collapsed:
                new_pool = []
                for free_block in free_pool:
                    if used_block.subnet_of(free_block):
                        new_pool.extend(list(free_block.address_exclude(used_block)))
                    elif not free_block.overlaps(used_block):
                        new_pool.append(free_block)
                free_pool = new_pool
            
            free_pool.sort(key=lambda n: int(n.network_address))
            free_space_cidrs = [str(f) for f in free_pool]
        else:
            free_space_cidrs = [str(parent_net)]
            
    return ValidationResult(
        has_overlaps=len(overlaps) > 0,
        overlaps=overlaps,
        parent_network=parent_network,
        free_space=free_space_cidrs
    )

def summarize_subnets(subnets: List[str]) -> 'SummarizeResult':
    from netpulse.subnet.models.subnet import SummarizeResult
    
    if not subnets:
        raise ValueError("No subnets provided for summarization.")
        
    parsed_networks = []
    for s in subnets:
        if not s.strip():
            continue
        try:
            net = ipaddress.ip_network(s.strip(), strict=False)
            parsed_networks.append(net)
        except ValueError:
            raise ValueError(f"Invalid subnet provided for summarization: '{s}'")
            
    if not parsed_networks:
        raise ValueError("No valid subnets found to summarize.")
        
    versions = {n.version for n in parsed_networks}
    if len(versions) > 1:
        raise ValueError("Cannot summarize mixed IPv4 and IPv6 addresses.")
        
    collapsed = list(ipaddress.collapse_addresses(parsed_networks))
    
    min_ip = min(n.network_address for n in collapsed)
    max_ip = max(n.broadcast_address if n.version == 4 else n.network_address + n.num_addresses - 1 for n in collapsed)
    
    version = collapsed[0].version
    max_bits = 32 if version == 4 else 128
    
    min_int = int(min_ip)
    max_int = int(max_ip)
    
    xor = min_int ^ max_int
    host_bits = xor.bit_length()
    prefix_len = max_bits - host_bits
    
    supernet = ipaddress.ip_network(f"{min_ip}/{prefix_len}", strict=False)
    
    total_ips = supernet.num_addresses
    provided_ips = sum(n.num_addresses for n in collapsed)
    slack_ips = total_ips - provided_ips
    
    return SummarizeResult(
        supernet=str(supernet),
        total_ips=total_ips,
        provided_ips=provided_ips,
        slack_ips=slack_ips,
        has_slack=slack_ips > 0
    )
