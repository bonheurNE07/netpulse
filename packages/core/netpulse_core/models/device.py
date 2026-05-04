import uuid
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, IPvAnyAddress, ConfigDict

class DeviceStatus(str, Enum):
    """Enumeration of possible device reachability states."""
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"

class Device(BaseModel):
    """
    The Core data model for a network device in the NetPulse ecosystem.
    
    This model is designed to be:
    1. Strongly typed (via Pydantic V2)
    2. Extensible (via the metadata dictionary)
    3. Persistence-ready (with UUID and UTC timestamps)
    """
    
    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "ip": "192.168.1.1",
                "mac": "00:11:22:33:44:55",
                "hostname": "router.local",
                "status": "up",
                "rtt_ms": 1.5,
                "metadata": {"vendor": "Cisco", "os": "IOS"}
            }
        }
    )
    
    # Identification Fields
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the device (UUID v4)."
    )
    ip: IPvAnyAddress = Field(
        ..., 
        description="The IP address of the device (IPv4 or IPv6)."
    )
    mac: Optional[str] = Field(
        None, 
        pattern=r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$",
        description="The hardware MAC address of the device."
    )
    hostname: Optional[str] = Field(
        None, 
        description="The resolved hostname or mDNS name of the device."
    )
    vendor: Optional[str] = Field(
        None, 
        description="The manufacturer/vendor name derived from the MAC OUI."
    )
    
    # Discovery & State Fields
    status: DeviceStatus = Field(
        default=DeviceStatus.UNKNOWN, 
        description="The current reachability status of the device."
    )
    rtt_ms: Optional[float] = Field(
        None, 
        description="The round-trip time in milliseconds recorded during discovery."
    )
    
    # Audit & Lifecycle Fields
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the device record was first created (UTC)."
    )
    last_seen: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="Timestamp when the device was last observed (UTC)."
    )
    
    # Extensibility
    metadata: Dict[str, Any] = Field(
        default_factory=dict, 
        description="A dictionary for plugin-specific data (e.g., SNMP, SSH, OS details)."
    )
