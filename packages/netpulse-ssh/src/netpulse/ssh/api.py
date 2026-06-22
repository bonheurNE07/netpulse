from fastapi import APIRouter, HTTPException, status, FastAPI
from typing import List, Optional
from pydantic import BaseModel, Field

from netpulse.ssh.models import SshHostConfig, SshExecutionAudit
from netpulse.ssh.runner import SshRunnerService

app = FastAPI(title="NetPulse SSH API")
ssh_router = APIRouter()

class SshExecuteHost(BaseModel):
    ip: str = Field(..., description="Target IP or hostname.")
    port: int = Field(22, description="SSH port.")

class SshExecuteRequest(BaseModel):
    hosts: List[SshExecuteHost] = Field(..., description="List of SSH hosts.")
    command: str = Field(..., description="SSH command to execute.")
    username: str = Field(..., description="SSH login username.")
    password: Optional[str] = Field(None, description="SSH login password.")
    enable_password: Optional[str] = Field(None, description="Cisco enable password.")
    jump_host: Optional[str] = Field(None, description="ProxyJump Bastion host (e.g., admin@bastion.local).")
    bastion_pass: Optional[str] = Field(None, description="Password for the Bastion host.")
    auto_negotiate: bool = Field(True, description="Enable key-exchange auto-negotiate fallbacks.")
    ignore_host_keys: bool = Field(True, description="Ignore host verification checks.")
    timeout_seconds: int = Field(10, description="Connection timeout.")

@ssh_router.post("/api/v1/ssh/execute", response_model=SshExecutionAudit, status_code=status.HTTP_200_OK)
async def execute_ssh_command(req: SshExecuteRequest):
    """
    Executes a command concurrently across one or multiple remote SSH hosts.
    Returns the audit trail containing stdout/stderr for each host.
    """
    try:
        hosts_config = []
        for h in req.hosts:
            hosts_config.append(SshHostConfig(
                ip=h.ip,
                port=h.port,
                username=req.username,
                password=req.password,
                enable_password=req.enable_password,
                jump_host=req.jump_host,
                bastion_pass=req.bastion_pass,
                auto_negotiate=req.auto_negotiate,
                ignore_host_keys=req.ignore_host_keys,
                timeout_seconds=req.timeout_seconds
            ))
            
        runner = SshRunnerService()
        audit = await runner.execute_concurrently(hosts_config, req.command)
        return audit
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "SshExecutionError",
                "message": f"Concurrent SSH runner failed: {e}"
            }
        )

app.include_router(ssh_router)
