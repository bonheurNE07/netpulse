import os
import pytest
import uuid
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone
import asyncssh

from netpulse.ssh.models import SshHostConfig, SshHostResult, SshExecutionAudit, SshStatus
from netpulse.ssh.runner import SmartSshClient, SshRunnerService

def test_ssh_models_instantiation():
    """Verify that SSH models validate inputs and set correct defaults."""
    config = SshHostConfig(
        ip="192.168.1.1",
        username="admin",
        password="secretpassword",
        enable_password="enablepwd"
    )
    assert config.ip == "192.168.1.1"
    assert config.port == 22
    assert config.username == "admin"
    assert config.password == "secretpassword"
    assert config.enable_password == "enablepwd"
    assert config.auto_negotiate is True
    assert config.ignore_host_keys is True

    result = SshHostResult(
        ip="192.168.1.1",
        status=SshStatus.SUCCESS,
        stdout="interface GigabitEthernet0/1\n ip address 192.168.1.1",
        latency_ms=45.2,
        negotiated_kex="diffie-hellman-group14-sha1",
        negotiated_cipher="aes128-cbc"
    )
    assert result.ip == "192.168.1.1"
    assert result.status == SshStatus.SUCCESS
    assert "GigabitEthernet0/1" in result.stdout
    assert result.latency_ms == 45.2
    assert result.negotiated_kex == "diffie-hellman-group14-sha1"
    assert result.negotiated_cipher == "aes128-cbc"


@pytest.mark.asyncio
@patch("asyncssh.connect", new_callable=AsyncMock)
async def test_ssh_client_success_standard(mock_connect):
    """Verify that SmartSshClient connects and executes successfully under standard handshakes."""
    mock_conn = MagicMock()
    mock_conn.wait_closed = AsyncMock()
    mock_conn.get_extra_info.side_effect = lambda key: {
        "kex_alg": "curve25519-sha256",
        "cipher_alg": "aes256-gcm@openssh.com"
    }.get(key)
    
    # Mock the terminal process stream
    mock_proc = AsyncMock()
    mock_proc.stdout.read.return_value = "GigabitEthernet0/1 is up, line protocol is up"
    mock_proc.stderr.read.return_value = ""
    mock_conn.create_process.return_value.__aenter__ = AsyncMock(return_value=mock_proc)
    mock_conn.create_process.return_value.__aexit__ = AsyncMock()

    mock_connect.return_value = mock_conn

    config = SshHostConfig(ip="192.168.1.5", username="admin", password="password")
    
    result = await SmartSshClient.connect_and_execute(config, "show interface description")
    
    assert result.status == SshStatus.SUCCESS
    assert "GigabitEthernet0/1" in result.stdout
    assert result.negotiated_kex == "curve25519-sha256"
    assert result.negotiated_cipher == "aes256-gcm@openssh.com"
    assert result.error_message is None
    
    # Ensure it only connected once (no legacy retry needed)
    mock_connect.assert_called_once()


@pytest.mark.asyncio
@patch("asyncssh.connect", new_callable=AsyncMock)
async def test_ssh_client_legacy_handshake_healing(mock_connect):
    """Verify that SmartSshClient retries connection with legacy ciphers if initial handshake fails."""
    # First connect attempt raises NegotiationError
    # Second connect attempt succeeds
    mock_conn = MagicMock()
    mock_conn.wait_closed = AsyncMock()
    mock_conn.get_extra_info.side_effect = lambda key: {
        "kex_alg": "diffie-hellman-group1-sha1",
        "cipher_alg": "3des-cbc"
    }.get(key)
    
    mock_proc = AsyncMock()
    mock_proc.stdout.read.return_value = "Legacy Cisco Switch Config..."
    mock_proc.stderr.read.return_value = ""
    mock_conn.create_process.return_value.__aenter__ = AsyncMock(return_value=mock_proc)
    mock_conn.create_process.return_value.__aexit__ = AsyncMock()

    mock_connect.side_effect = [
        asyncssh.misc.ProtocolError("Key exchange failed: no matching algorithms"),
        mock_conn
    ]

    config = SshHostConfig(ip="192.168.1.10", username="admin", password="password", auto_negotiate=True)
    
    result = await SmartSshClient.connect_and_execute(config, "show run")
    
    assert result.status == SshStatus.SUCCESS
    assert "Legacy Cisco Switch" in result.stdout
    assert result.negotiated_kex == "diffie-hellman-group1-sha1"
    assert result.negotiated_cipher == "3des-cbc"
    
    # Ensure it connected twice (first fail, second legacy retry)
    assert mock_connect.call_count == 2
    # Second call must have legacy algorithms configured
    legacy_call_args = mock_connect.call_args_list[1][1]
    assert "diffie-hellman-group1-sha1" in legacy_call_args["kex_algs"]
    assert "3des-cbc" in legacy_call_args["encryption_algs"]


@pytest.mark.asyncio
@patch("asyncssh.connect", new_callable=AsyncMock)
async def test_ssh_runner_concurrent_execution(mock_connect):
    """Verify that SshRunnerService executes commands across multiple hosts in parallel and saves results."""
    mock_conn = MagicMock()
    mock_conn.wait_closed = AsyncMock()
    mock_conn.get_extra_info.side_effect = lambda key: {
        "kex_alg": "curve25519-sha256",
        "cipher_alg": "aes256-gcm@openssh.com"
    }.get(key)
    
    mock_proc = AsyncMock()
    mock_proc.stdout.read.return_value = "Command output"
    mock_proc.stderr.read.return_value = ""
    mock_conn.create_process.return_value.__aenter__ = AsyncMock(return_value=mock_proc)
    mock_conn.create_process.return_value.__aexit__ = AsyncMock()
    mock_connect.return_value = mock_conn

    # Multi-host targets
    hosts = [
        SshHostConfig(ip="10.0.0.1", username="cisco", password="pwd"),
        SshHostConfig(ip="10.0.0.2", username="cisco", password="pwd")
    ]
    
    runner = SshRunnerService()
    
    audit = await runner.execute_concurrently(hosts, "show clock")
    
    assert isinstance(audit, SshExecutionAudit)
    assert audit.success_count == 2
    assert audit.failed_count == 0
    assert len(audit.results) == 2
    assert audit.results[1].stdout == "Command output"

@pytest.mark.asyncio
@patch("asyncssh.scp", new_callable=AsyncMock)
@patch("asyncssh.connect", new_callable=AsyncMock)
async def test_ssh_client_scp_push(mock_connect, mock_scp):
    """Verify that SmartSshClient correctly executes scp_push."""
    mock_conn = MagicMock()
    mock_conn.wait_closed = AsyncMock()
    mock_conn.get_extra_info.side_effect = lambda key: {
        "kex_alg": "curve25519-sha256",
        "cipher_alg": "aes256-gcm@openssh.com"
    }.get(key)
    mock_connect.return_value = mock_conn

    config = SshHostConfig(ip="192.168.1.20", username="admin", password="password")
    
    result = await SmartSshClient.scp_push(config, "local.bin", "/remote/path/local.bin")
    
    assert result.status == SshStatus.SUCCESS
    assert "Successfully pushed" in result.stdout
    assert result.negotiated_kex == "curve25519-sha256"
    assert result.negotiated_cipher == "aes256-gcm@openssh.com"
    
    mock_connect.assert_called_once()
    mock_scp.assert_called_once_with("local.bin", (mock_conn, "/remote/path/local.bin"))

@pytest.mark.asyncio
@patch("os.makedirs")
@patch("asyncssh.scp", new_callable=AsyncMock)
@patch("asyncssh.connect", new_callable=AsyncMock)
async def test_ssh_client_scp_pull(mock_connect, mock_scp, mock_makedirs):
    """Verify that SmartSshClient correctly executes scp_pull and creates directories."""
    mock_conn = MagicMock()
    mock_conn.wait_closed = AsyncMock()
    mock_conn.get_extra_info.side_effect = lambda key: {
        "kex_alg": "curve25519-sha256",
        "cipher_alg": "aes256-gcm@openssh.com"
    }.get(key)
    mock_connect.return_value = mock_conn

    config = SshHostConfig(ip="192.168.1.30", username="admin", password="password")
    
    result = await SmartSshClient.scp_pull(config, "/remote/path/config.txt", "./backups")
    
    assert result.status == SshStatus.SUCCESS
    assert "Successfully pulled" in result.stdout
    
    mock_connect.assert_called_once()
    mock_makedirs.assert_called_once_with("./backups/192.168.1.30", exist_ok=True)
    mock_scp.assert_called_once_with((mock_conn, "/remote/path/config.txt"), "./backups/192.168.1.30/config.txt")
