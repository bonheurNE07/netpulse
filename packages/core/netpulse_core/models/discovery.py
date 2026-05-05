import uuid
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, IPvAnyNetwork, ConfigDict

from .device import Device

class DiscoveryMethod(str, Enum):
    """Protocol methods used for network discovery."""
    ARP = "arp"
    ICMP = "icmp"
    UDP = "udp"
    TCP = "tcp"

class DiscoveryResult(BaseModel):
    """
    Schema representing the complete result of a network discovery operation.
    
    Refined based on data consistency and observability requirements.
    """
    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
        populate_by_name=True,
        arbitrary_types_allowed=True
    )

    # Identification & Scope
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the scan session."
    )
    network: IPvAnyNetwork = Field(
        ...,
        description="The CIDR network range targeted by the scan."
    )
    
    # Execution Metadata
    methods: List[DiscoveryMethod] = Field(
        default_factory=list,
        description="The discovery protocols used during this session."
    )
    status: str = Field(
        default="completed",
        description="Execution status of the scan (completed, partial, failed)."
    )
    errors: List[str] = Field(
        default_factory=list,
        description="List of error messages encountered during scanning."
    )
    
    # Data
    devices: List[Device] = Field(
        default_factory=list,
        description="The list of devices discovered during the scan."
    )
    
    # Timing (UTC)
    started_at: datetime = Field(
        ...,
        description="The timestamp when the scan was initiated."
    )
    finished_at: datetime = Field(
        ...,
        description="The timestamp when the scan was completed."
    )
    
    # Analytics & Future Extensibility
    stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Aggregated statistics (e.g., hosts scanned, response rate)."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom data for plugins or monitoring."
    )

    @property
    def duration_s(self) -> float:
        """Calculates scan duration in seconds."""
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def total_discovered(self) -> int:
        """Derived property ensuring data consistency for discovered 'up' devices."""
        return len([d for d in self.devices if d.status == "up"])
