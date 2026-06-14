# API Reference

If you want to use the subnet algorithms natively inside your own Python projects without using the REST API or CLI, `netpulse-subnet` exposes strongly-typed, pure Python services.

## Models

### `SubnetInfo`
Represents comprehensive details about a single subnet calculation.
```python
from netpulse.subnet.models.subnet import SubnetInfo

class SubnetInfo(BaseModel):
    ip: str
    network_cidr: str
    network_address: str
    prefix_length: int
    netmask: str
    wildcard_mask: str
    broadcast_address: str
    first_usable: str
    last_usable: str
    total_hosts: int
    binary_representation: Dict[str, str]
```

### `VLSMAllocation` & `VLSMResult`
Represents the result of a VLSM operation.
```python
from netpulse.subnet.models.subnet import VLSMResult, VLSMAllocation

class VLSMAllocation(BaseModel):
    name: str
    requested_hosts: int
    allocated_hosts: int
    network_cidr: str
    netmask: str
    usable_range: str
    broadcast: str
    wastage_percentage: float

class VLSMResult(BaseModel):
    parent_network: str
    allocations: List[VLSMAllocation]
    unallocated_blocks: List[Dict[str, Any]]
```

## Services

### `calculate_subnet_info(ip: str, mask_or_prefix: str) -> SubnetInfo`
Given an IP address (e.g., `192.168.1.50`) and either a prefix length (e.g., `24`) or a dot-decimal netmask (e.g., `255.255.255.0`), this returns the `SubnetInfo` model.

### `split_fixed_length(parent_network: str, subnets_count: int = None, hosts_per_subnet: int = None) -> List[str]`
Splits a parent CIDR into equal-sized subnets. You must provide either `subnets_count` OR `hosts_per_subnet`, but not both. Returns a list of CIDR strings.

### `allocate_vlsm(parent_network: str, requirements: List[Dict[str, Any]]) -> VLSMResult`
Performs optimal VLSM allocation. `requirements` must be a list of dictionaries containing `name` and `hosts` keys.
```python
from netpulse.subnet.services.subnet import allocate_vlsm

result = allocate_vlsm(
    "192.168.1.0/24", 
    [{"name": "HR", "hosts": 120}, {"name": "Dev", "hosts": 50}]
)
print(result.allocations[0].network_cidr) # 192.168.1.0/25
```

### `find_containing_subnet(ip: str, subnets: List[str]) -> Optional[str]`
Given an IP address and a list of CIDR network strings, this efficiently determines which network the IP belongs to. Returns the matching CIDR string or `None`.
