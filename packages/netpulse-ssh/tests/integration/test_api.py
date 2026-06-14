import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from netpulse.ssh.api import app
from netpulse.ssh.models import SshExecutionAudit, SshHostResult, SshStatus

def test_api_execute_ssh_command_success():
    """Verify POST /api/v1/ssh/execute returns execution audit successfully."""
    client = TestClient(app)
    
    mock_audit = SshExecutionAudit(
        command="show version",
        targets=["192.168.1.1"],
        success_count=1,
        failed_count=0,
        results=[
            SshHostResult(
                ip="192.168.1.1",
                status=SshStatus.SUCCESS,
                stdout="Cisco IOS Software",
                latency_ms=12.5,
                negotiated_kex="curve25519-sha256",
                negotiated_cipher="aes256-gcm@openssh.com"
            )
        ]
    )
    
    with patch("netpulse.ssh.api.SshRunnerService.execute_concurrently", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_audit
        
        payload = {
            "hosts": [{"ip": "192.168.1.1", "port": 22}],
            "command": "show version",
            "username": "admin",
            "password": "password",
            "timeout_seconds": 10
        }
        
        response = client.post("/api/v1/ssh/execute", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["command"] == "show version"
        assert data["success_count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["ip"] == "192.168.1.1"
        assert data["results"][0]["stdout"] == "Cisco IOS Software"

def test_api_execute_ssh_command_failure():
    """Verify POST /api/v1/ssh/execute handles backend runner exceptions and returns 500."""
    client = TestClient(app)
    
    with patch("netpulse.ssh.api.SshRunnerService.execute_concurrently", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = Exception("Kernel Panic in asyncssh loop")
        
        payload = {
            "hosts": [{"ip": "10.0.0.1", "port": 22}],
            "command": "reboot",
            "username": "root",
            "password": "password"
        }
        
        response = client.post("/api/v1/ssh/execute", json=payload)
        
        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["error"] == "SshExecutionError"
        assert "Kernel Panic" in data["detail"]["message"]
