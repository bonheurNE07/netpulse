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

def test_cli_scp_push_success():
    """Verify that the scp push command invokes the runner and prints results successfully."""
    mock_audit = SshExecutionAudit(
        command="scp push ./firmware.bin -> /flash/",
        targets=["10.0.0.5"],
        success_count=1,
        failed_count=0,
        results=[
            SshHostResult(
                ip="10.0.0.5",
                status=SshStatus.SUCCESS,
                stdout="Successfully pushed ./firmware.bin to /flash/",
                latency_ms=120.5,
                negotiated_kex="curve25519-sha256",
                negotiated_cipher="aes256-gcm@openssh.com"
            )
        ]
    )
    
    with patch("netpulse.ssh.cli.SshRunnerService.execute_scp_push_concurrently", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_audit
        
        # In cli.py, the command is attached to scp_app which is attached as 'scp' to the main app.
        # So we invoke app with ["scp", "push", ...]
        result = runner.invoke(app, ["scp", "push", "10.0.0.5", "--src", "./firmware.bin", "--dest", "/flash/", "-u", "admin", "-p", "password"])
        
        assert result.exit_code == 0
        assert "SCP Push Summary" in result.stdout
        assert "10.0.0.5" in result.stdout
        assert "SUCCESS" in result.stdout
        assert "Successfully pushed" in result.stdout

def test_cli_scp_pull_success():
    """Verify that the scp pull command invokes the runner and prints results successfully."""
    mock_audit = SshExecutionAudit(
        command="scp pull /etc/nginx/nginx.conf -> ./backups",
        targets=["10.0.0.6"],
        success_count=1,
        failed_count=0,
        results=[
            SshHostResult(
                ip="10.0.0.6",
                status=SshStatus.SUCCESS,
                stdout="Successfully pulled /etc/nginx/nginx.conf to ./backups/10.0.0.6/nginx.conf",
                latency_ms=45.2,
                negotiated_kex="curve25519-sha256",
                negotiated_cipher="aes256-gcm@openssh.com"
            )
        ]
    )
    
    with patch("netpulse.ssh.cli.SshRunnerService.execute_scp_pull_concurrently", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_audit
        
        result = runner.invoke(app, ["scp", "pull", "10.0.0.6", "--src", "/etc/nginx/nginx.conf", "--dest", "./backups", "-u", "admin", "-p", "password"])
        
        assert result.exit_code == 0
        assert "SCP Pull Summary" in result.stdout
        assert "10.0.0.6" in result.stdout
        assert "Successfully pulled" in result.stdout

def test_cli_execute_jump_host():
    """Verify that the execute command correctly passes jump_host arguments."""
    mock_audit = SshExecutionAudit(
        command="uptime",
        targets=["10.0.0.5"],
        success_count=1,
        failed_count=0,
        results=[
            SshHostResult(
                ip="10.0.0.5",
                status=SshStatus.SUCCESS,
                stdout="up",
                latency_ms=10.0,
            )
        ]
    )
    
    with patch("netpulse.ssh.cli.SshRunnerService.execute_concurrently", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_audit
        
        result = runner.invoke(app, [
            "execute", "10.0.0.5", 
            "-c", "uptime", 
            "-u", "admin", 
            "-p", "password", 
            "-J", "bastion@192.168.1.100", 
            "--bastion-pass", "proxy_secret"
        ])
        
        assert result.exit_code == 0
        mock_exec.assert_called_once()
        hosts_config = mock_exec.call_args[0][0]
        assert hosts_config[0].jump_host == "bastion@192.168.1.100"
        assert hosts_config[0].bastion_pass == "proxy_secret"
