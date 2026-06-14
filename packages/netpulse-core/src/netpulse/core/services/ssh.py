import asyncio
import time
import logging
import asyncssh
from typing import Optional, Tuple
from netpulse.core.models.ssh import SshHostConfig, SshHostResult, SshStatus

logger = logging.getLogger(__name__)

class TrustingSSHClient(asyncssh.SSHClient):
    """Custom SSH client that trusts all host keys to prevent IP-reassignment blockage."""
    def validate_host_key(self, host: str, port: int, key: bytes, fingerprint: str) -> bool:
        return True

class SmartSshClient:
    """
    Highly resilient, non-blocking SSH client optimized for network engineers.
    Automatically handles legacy cryptographic negotiation, pagination pager suppression,
    host key changes, and privilege enable escalation.
    """

    @classmethod
    async def connect_and_execute(cls, config: SshHostConfig, command: str) -> SshHostResult:
        """
        Resiliently connects to a host via SSH, performs command executions,
        and logs performance/cryptographic parameters.
        """
        ip = config.ip
        port = config.port
        username = config.username
        password = config.password
        enable_password = config.enable_password
        timeout = config.timeout_seconds

        start_time = time.perf_counter()
        
        # Standard modern connection options
        connect_opts = {
            "host": ip,
            "port": port,
            "username": username,
            "password": password,
            "login_timeout": timeout,
        }

        # Bypass host key checking using our custom validator
        if config.ignore_host_keys:
            connect_opts["client_factory"] = TrustingSSHClient

        conn = None
        negotiated_kex = None
        negotiated_cipher = None
        used_fallback = False

        try:
            # 1. Attempt connection using modern secure algorithms
            try:
                conn = await asyncssh.connect(**connect_opts)
            except (asyncssh.misc.ProtocolError, asyncssh.misc.DisconnectError) as e:
                # Catch cryptographic key exchange or cipher mismatch errors
                if config.auto_negotiate:
                    logger.warning(
                        f"Handshake failed with {ip}:{port} ({e}). Retrying with legacy cryptographic support..."
                    )
                    used_fallback = True
                    
                    # Explicitly enable legacy KEX, signature (host keys), and encryption ciphers
                    legacy_opts = {
                        **connect_opts,
                        "kex_algs": [
                            "diffie-hellman-group1-sha1",
                            "diffie-hellman-group14-sha1",
                            "diffie-hellman-group-exchange-sha1",
                            "diffie-hellman-group-exchange-sha256",
                            "ecdh-sha2-nistp256",
                            "ecdh-sha2-nistp384",
                            "ecdh-sha2-nistp521",
                        ],
                        "encryption_algs": [
                            "aes128-cbc",
                            "aes192-cbc",
                            "aes256-cbc",
                            "3des-cbc",
                            "aes128-ctr",
                            "aes192-ctr",
                            "aes256-ctr",
                        ],
                        "signature_algs": [
                            "ssh-rsa",
                            "ssh-dss",
                            "ecdsa-sha2-nistp256",
                            "ssh-ed25519",
                        ],
                    }
                    conn = await asyncssh.connect(**legacy_opts)
                else:
                    raise e

            # Log successfully negotiated parameters
            negotiated_kex = conn.get_extra_info("kex_alg")
            negotiated_cipher = conn.get_extra_info("cipher_alg")

            # 2. Interactive execution shell session (VT100)
            # This enables handling Cisco enable prompts and suppressing --More-- page breaks
            stdout_str, stderr_str = await cls._execute_interactive(
                conn=conn,
                command=command,
                enable_password=enable_password,
                timeout=timeout
            )

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            return SshHostResult(
                ip=ip,
                status=SshStatus.SUCCESS,
                stdout=stdout_str,
                stderr=stderr_str if stderr_str else None,
                latency_ms=round(latency_ms, 2),
                negotiated_kex=negotiated_kex,
                negotiated_cipher=negotiated_cipher
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            error_msg = str(e)
            if used_fallback:
                error_msg = f"Legacy Handshake Fail: {error_msg}"
            
            return SshHostResult(
                ip=ip,
                status=SshStatus.FAILED,
                latency_ms=round(latency_ms, 2),
                error_message=error_msg
            )
        finally:
            if conn:
                conn.close()
                await conn.wait_closed()

    @classmethod
    async def _execute_interactive(
        cls, 
        conn: asyncssh.SSHClientConnection, 
        command: str, 
        enable_password: Optional[str] = None,
        timeout: int = 10
    ) -> Tuple[str, str]:
        """
        Emulates a virtual terminal (pty) session to run enable escalations
        and suppress terminal pagination natively.
        """
        # Open interactive virtual terminal process
        async with conn.create_process(term_type='vt100') as proc:
            # 1. Handle Cisco privilege exec escalation
            if enable_password:
                proc.stdin.write("enable\n")
                await asyncio.sleep(0.15)
                proc.stdin.write(f"{enable_password}\n")
                await asyncio.sleep(0.15)

            # 2. Suppress terminal pagination (works on Cisco IOS / Cisco Mock environments)
            # Non-Cisco environments will ignore/error this but proceed cleanly
            proc.stdin.write("terminal length 0\n")
            await asyncio.sleep(0.1)

            # 3. Execute the actual command
            proc.stdin.write(f"{command}\n")
            await asyncio.sleep(0.15)
            
            # Exit session cleanly
            proc.stdin.write("exit\n")
            
            # Read streams asynchronously with safety timeout
            try:
                stdout_data = await asyncio.wait_for(proc.stdout.read(), timeout=timeout)
                stderr_data = await asyncio.wait_for(proc.stderr.read(), timeout=timeout)
            except asyncio.TimeoutError:
                stdout_data = "Error: Interactive terminal execution timed out."
                stderr_data = ""

            return stdout_data, stderr_data
