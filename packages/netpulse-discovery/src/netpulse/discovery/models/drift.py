import uuid
from typing import List, Optional
from pydantic import BaseModel, Field

from netpulse.discovery.models.device import Device


class DeviceChange(BaseModel):
    """
    Detailed shifts for a single host matching across both benchmark and target sweeps.
    """
    ip: str = Field(..., description="The IP address of the modified host.")
    mac_old: Optional[str] = Field(None, description="The old hardware MAC address.")
    mac_new: Optional[str] = Field(None, description="The new hardware MAC address.")
    rtt_old: Optional[float] = Field(None, description="The old response time in milliseconds.")
    rtt_new: Optional[float] = Field(None, description="The new response time in milliseconds.")
    status_old: str = Field(..., description="The previous reachability status.")
    status_new: str = Field(..., description="The updated reachability status.")


class DriftResult(BaseModel):
    """
    Aggregated comparison boundaries across two historical scans.
    """
    network: str = Field(..., description="The targeted network CIDR block.")
    old_scan_id: Optional[uuid.UUID] = Field(None, description="UUID of the old benchmark scan.")
    new_scan_id: uuid.UUID = Field(..., description="UUID of the new comparison scan.")
    old_timestamp: Optional[str] = Field(None, description="UTC ISO timestamp of the old scan.")
    new_timestamp: str = Field(..., description="UTC ISO timestamp of the new scan.")
    
    joined: List[Device] = Field(default_factory=list, description="Newly discovered hosts.")
    left: List[Device] = Field(default_factory=list, description="Hosts that went offline or vanished.")
    modified: List[DeviceChange] = Field(default_factory=list, description="Hosts with shifts in MAC or RTT parameters.")
    unchanged: List[Device] = Field(default_factory=list, description="Hosts present in both scans without state updates.")
