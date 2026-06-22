import uuid
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict

class SshStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"

class SshHostConfig(BaseModel):
    """Configuration for an individual SSH connection target."""
    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
        populate_by_name=True
    )
    ip: str = Field(..., description="Target host IP address or hostname.")
    port: int = Field(22, description="SSH port (defaults to 22).")
    username: str = Field(..., description="SSH login username.")
    password: Optional[str] = Field(None, description="SSH login password.")
    enable_password: Optional[str] = Field(None, description="Cisco enable password.")
    ssh_key: Optional[str] = Field(None, description="Path to SSH private key.")
    jump_host: Optional[str] = Field(None, description="ProxyJump Bastion host (e.g., admin@bastion.local).")
    bastion_pass: Optional[str] = Field(None, description="Password for the Bastion host.")
    auto_negotiate: bool = Field(True, description="Attempt dynamic legacy cipher negotiation if handshake fails.")
    ignore_host_keys: bool = Field(True, description="Bypass strict SSH host key checking.")
    timeout_seconds: int = Field(10, description="SSH connection timeout.")

class SshHostResult(BaseModel):
    """Execution result details for an individual target host."""
    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True
    )
    ip: str = Field(..., description="Target host IP address.")
    status: SshStatus = Field(..., description="Connection or execution outcome status.")
    stdout: Optional[str] = Field(None, description="Command execution standard output.")
    stderr: Optional[str] = Field(None, description="Command execution standard error.")
    latency_ms: Optional[float] = Field(None, description="Execution latency/duration in milliseconds.")
    negotiated_kex: Optional[str] = Field(None, description="The negotiated key exchange algorithm.")
    negotiated_cipher: Optional[str] = Field(None, description="The negotiated encryption cipher.")
    error_message: Optional[str] = Field(None, description="Detailed failure reason if status is FAILED.")

class SshExecutionAudit(BaseModel):
    """Aggregate model representing a multi-host SSH execution session."""
    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique execution audit UUID.")
    command: str = Field(..., description="The command executed across the targets.")
    targets: List[str] = Field(..., description="Target host IP addresses.")
    success_count: int = Field(..., description="Number of hosts successfully executed.")
    failed_count: int = Field(..., description="Number of hosts that failed.")
    executed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the audit was generated (UTC)."
    )
    results: List[SshHostResult] = Field(..., description="Individual execution results.")

class PlaybookExpect(BaseModel):
    prompt: str = Field(..., description="Regex pattern to match in standard output.")
    send: str = Field(..., description="String to send to standard input when the pattern is matched.")

class PlaybookTask(BaseModel):
    name: str = Field(..., description="Name of the task.")
    command: str = Field(..., description="Command to execute.")
    expect: Optional[List[PlaybookExpect]] = Field(None, description="Optional list of expect rules for interactive commands.")
    timeout: Optional[int] = Field(None, description="Optional custom timeout for this specific task in seconds.")

class Playbook(BaseModel):
    name: str = Field("Playbook", description="Name of the playbook.")
    tasks: List[PlaybookTask] = Field(..., description="Sequential list of tasks to execute.")

class InventoryHost(BaseModel):
    ip: str = Field(..., description="Host IP address.")
    username: Optional[str] = Field(None, description="SSH username. Overrides global or group settings.")
    password: Optional[str] = Field(None, description="SSH password. Overrides global or group settings.")
    enable_password: Optional[str] = Field(None, description="Cisco enable password.")
    ssh_key: Optional[str] = Field(None, description="Path to SSH private key.")
    port: Optional[int] = Field(None, description="SSH port.")

class InventoryGroup(BaseModel):
    hosts: List[InventoryHost] = Field(..., description="List of hosts in the group.")

class Inventory(BaseModel):
    groups: Dict[str, InventoryGroup] = Field(..., description="Mapping of group names to their respective hosts.")
