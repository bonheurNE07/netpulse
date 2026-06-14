import pytest
from unittest.mock import patch, AsyncMock
from typer.testing import CliRunner

from netpulse.ssh.cli import app
from netpulse.ssh.models import SshExecutionAudit, SshHostResult, SshStatus

runner = CliRunner()

def test_cli_execute_ssh_command_success():
    """Verify that the execute command invokes the runner and prints results successfully."""
    mock_audit = SshExecutionAudit(
        command="show version",
        targets=["10.0.0.1"],
        success_count=1,
        failed_count=0,
        results=[
            SshHostResult(
                ip="10.0.0.1",
                status=SshStatus.SUCCESS,
                stdout="Cisco IOS Software",
                latency_ms=15.5,
                negotiated_kex="curve25519-sha256",
                negotiated_cipher="aes256-gcm@openssh.com"
            )
        ]
    )
    
    with patch("netpulse.ssh.cli.SshRunnerService.execute_concurrently", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_audit
        
        result = runner.invoke(app, ["execute", "10.0.0.1", "-c", "show version", "-u", "admin", "-p", "password"])
        
        assert result.exit_code == 0
        assert "SSH Execution Summary" in result.stdout
        assert "10.0.0.1" in result.stdout
        assert "SUCCESS" in result.stdout
        assert "Cisco IOS Software" in result.stdout

def test_cli_execute_ssh_command_failure():
    """Verify that the execute command handles failures cleanly and prints them."""
    mock_audit = SshExecutionAudit(
        command="show version",
        targets=["10.0.0.1"],
        success_count=0,
        failed_count=1,
        results=[
            SshHostResult(
                ip="10.0.0.1",
                status=SshStatus.FAILED,
                error_message="Authentication failed: invalid username or password.",
                latency_ms=10.0
            )
        ]
    )
    
    with patch("netpulse.ssh.cli.SshRunnerService.execute_concurrently", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_audit
        
        result = runner.invoke(app, ["execute", "10.0.0.1", "-c", "show version", "-u", "admin", "-p", "wrongpassword"])
        
        assert result.exit_code == 0
        assert "10.0.0.1" in result.stdout
        assert "FAILED" in result.stdout
        assert "Authentication failed" in result.stdout
        assert "Total Failed: 1" in result.stdout
