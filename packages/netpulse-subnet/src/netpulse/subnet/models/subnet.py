from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, ConfigDict, IPvAnyNetwork, IPvAnyAddress, field_validator


class SubnetInfo(BaseModel):
    """
    Detailed network boundary information for an IP and its subnet mask/prefix.
    """
    model_config = ConfigDict(populate_by_name=True)

    ip: IPvAnyAddress = Field(..., description="The queried IP address.")
    network_cidr: str = Field(..., description="The network address in CIDR format (e.g. 192.168.1.0/24).")
    network_address: IPvAnyAddress = Field(..., description="The base network address.")
    prefix_length: int = Field(..., ge=0, le=128, description="The network prefix length.")
    netmask: IPvAnyAddress = Field(..., description="The subnet mask.")
    wildcard_mask: IPvAnyAddress = Field(..., description="The wildcard/host mask.")
    broadcast_address: Optional[IPvAnyAddress] = Field(None, description="The broadcast address (IPv4 only).")
    first_usable: Optional[IPvAnyAddress] = Field(None, description="The first assignable host IP.")
    last_usable: Optional[IPvAnyAddress] = Field(None, description="The last assignable host IP.")
    total_hosts: int = Field(..., description="Total usable/assignable host IPs in the subnet.")
    binary_representation: Dict[str, str] = Field(
        default_factory=dict,
        description="Aligned binary representations of the IP, subnet mask, and network address."
    )


class VLSMRequirement(BaseModel):
    """
    A single subnet host size request for VLSM allocation.
    """
    name: str = Field(..., description="Label or name of the subnet requirement (e.g., Department A).")
    hosts: int = Field(..., ge=1, description="Number of required host IP addresses.")


class VLSMAllocation(BaseModel):
    """
    Subnet assigned to satisfy a specific host requirement in VLSM.
    """
    name: str = Field(..., description="Label of the satisfied requirement.")
    hosts_requested: int = Field(..., description="The requested number of host IPs.")
    hosts_allocated: int = Field(..., description="Total usable host IPs available in the allocated block.")
    network_cidr: str = Field(..., description="Allocated subnet in CIDR notation (e.g., 192.168.1.0/25).")
    netmask: str = Field(..., description="Subnet netmask (e.g., 255.255.255.128).")
    broadcast: str = Field(..., description="Subnet broadcast address.")
    first_usable: str = Field(..., description="First usable IP address.")
    last_usable: str = Field(..., description="Last usable IP address.")
    wastage_percent: float = Field(..., description="Percentage of allocated host space that is wasted.")


class VLSMResult(BaseModel):
    """
    The full grid resulting from a VLSM allocation session.
    """
    parent_network: str = Field(..., description="The original parent subnet range in CIDR notation.")
    allocations: List[VLSMAllocation] = Field(default_factory=list, description="Subnets successfully allocated.")
    unallocated_requirements: List[VLSMRequirement] = Field(
        default_factory=list,
        description="Requirements that could not be satisfied due to subnet address exhaustion."
    )
    free_space_remaining: List[str] = Field(
        default_factory=list,
        description="CIDR strings of the remaining unallocated free subnets."
    )

class OverlapPair(BaseModel):
    """
    Represents two explicitly overlapping subnets.
    """
    subnet1: str = Field(..., description="The first conflicting CIDR block.")
    subnet2: str = Field(..., description="The second conflicting CIDR block.")

class ValidationResult(BaseModel):
    """
    Result of a massive subnet overlap check and free space validation.
    """
    has_overlaps: bool = Field(..., description="True if any subnets conflict.")
    overlaps: List[OverlapPair] = Field(default_factory=list, description="List of all detected overlaps.")
    parent_network: Optional[str] = Field(None, description="The parent CIDR block, if provided.")
    free_space: List[str] = Field(default_factory=list, description="Unallocated remaining subnets in the parent block.")

class SummarizeResult(BaseModel):
    supernet: str = Field(..., description="The tightest covering CIDR block")
    total_ips: int = Field(..., description="Total IP capacity of the supernet")
    provided_ips: int = Field(..., description="Total IP capacity of the provided subnets")
    slack_ips: int = Field(..., description="Difference between total_ips and provided_ips")
    has_slack: bool = Field(..., description="True if the supernet covers space not explicitly provided")
