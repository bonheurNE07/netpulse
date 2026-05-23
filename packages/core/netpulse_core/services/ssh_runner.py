import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from netpulse_core.models.ssh import SshHostConfig, SshHostResult, SshExecutionAudit, SshStatus
from netpulse_core.services.ssh import SmartSshClient
from netpulse_core.services.db import DatabaseService

class SshRunnerService:
    """
    Orchestrates high-speed, parallel SSH command executions across multiple network hosts.
    Aggregates outcomes and stores persistent audit trails in local storage.
    """

    def __init__(self, db_service: Optional[DatabaseService] = None):
        self.db = db_service or DatabaseService()

    async def execute_concurrently(self, hosts: List[SshHostConfig], command: str) -> SshExecutionAudit:
        """
        Concurrently executes a command across multiple host configurations.
        
        Args:
            hosts: List of SshHostConfig models
            command: Configuration or diagnostic command string to run
            
        Returns:
            An SshExecutionAudit model aggregating all host executions and metrics
        """
        if not hosts:
            return SshExecutionAudit(
                command=command,
                targets=[],
                success_count=0,
                failed_count=0,
                results=[]
            )

        # Trigger concurrent executions using asyncio.gather
        tasks = [SmartSshClient.connect_and_execute(cfg, command) for cfg in hosts]
        results: List[SshHostResult] = await asyncio.gather(*tasks)

        # Count outcomes and targets
        success_count = sum(1 for res in results if res.status == SshStatus.SUCCESS)
        failed_count = sum(1 for res in results if res.status == SshStatus.FAILED)
        targets = [cfg.ip for cfg in hosts]

        # Construct unified execution audit model
        audit = SshExecutionAudit(
            command=command,
            targets=targets,
            success_count=success_count,
            failed_count=failed_count,
            results=results,
            executed_at=datetime.now(timezone.utc)
        )

        # Persist audit logs inside SQLite
        try:
            self.db.save_ssh_audit(audit)
        except Exception:
            # Resiliency fallback: database errors do not halt network execution results
            pass

        return audit
