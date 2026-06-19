import asyncio
import time
import logging
import sys 
import os
import re
import asyncssh
from typing import List, Optional, Tuple
from datetime import datetime, timezone

from netpulse.ssh.models import SshHostConfig, SshHostResult, SshStatus, SshExecutionAudit, Playbook

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

        if config.ssh_key:
            connect_opts["client_keys"] = [config.ssh_key]

        # Bypass host key checking using our custom validator
        if config.ignore_host_keys:
            connect_opts["client_factory"] = TrustingSSHClient
            connect_opts["known_hosts"] = None

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

            # Clean interactive stdout to remove MOTD, command echoes, and exit sequence
            if stdout_str:
                if "terminal length 0" in stdout_str:
                    stdout_str = stdout_str.split("terminal length 0")[-1]
                if command in stdout_str:
                    stdout_str = stdout_str.split(command, 1)[-1]
                if "exit" in stdout_str:
                    stdout_str = stdout_str.rsplit("exit", 1)[0]
                stdout_str = stdout_str.strip()

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
    async def connect_and_shell(cls, config: SshHostConfig, term_type: str = "xterm-256color") -> None:
        """
        Resiliently connects to a host via SSH and delegates local terminal
        standard IO to a remote interactive PTY session.
        """
        ip = config.ip
        port = config.port
        username = config.username
        password = config.password
        timeout = config.timeout_seconds
        
        connect_opts = {
            "host": ip,
            "port": port,
            "username": username,
            "password": password,
            "login_timeout": timeout,
        }

        if config.ssh_key:
            connect_opts["client_keys"] = [config.ssh_key]

        if config.ignore_host_keys:
            connect_opts["client_factory"] = TrustingSSHClient
            connect_opts["known_hosts"] = None

        conn = None
        try:
            try:
                conn = await asyncssh.connect(**connect_opts)
            except (asyncssh.misc.ProtocolError, asyncssh.misc.DisconnectError) as e:
                if config.auto_negotiate:
                    logger.warning(f"Handshake failed with {ip}:{port} ({e}). Retrying with legacy cryptographic support...")
                    legacy_opts = {
                        **connect_opts,
                        "kex_algs": ["diffie-hellman-group1-sha1", "diffie-hellman-group14-sha1", "diffie-hellman-group-exchange-sha1", "diffie-hellman-group-exchange-sha256", "ecdh-sha2-nistp256", "ecdh-sha2-nistp384", "ecdh-sha2-nistp521"],
                        "encryption_algs": ["aes128-cbc", "aes192-cbc", "aes256-cbc", "3des-cbc", "aes128-ctr", "aes192-ctr", "aes256-ctr"],
                        "signature_algs": ["ssh-rsa", "ssh-dss", "ecdsa-sha2-nistp256", "ssh-ed25519"],
                    }
                    conn = await asyncssh.connect(**legacy_opts)
                else:
                    raise e
            
            if sys.platform == "win32":
                # Enable VT100 Virtual Terminal Processing on Windows to render ANSI escape sequences
                import ctypes
                import msvcrt
                try:
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
                    mode = ctypes.c_uint()
                    kernel32.GetConsoleMode(handle, ctypes.byref(mode))
                    kernel32.SetConsoleMode(handle, mode.value | 0x0004)
                except Exception:
                    pass

                osc_escape = re.compile(r'\x1b\].*?(?:\x1b\\|\x07)')
                bracketed_paste = re.compile(r'\x1b\[\?2004[hl]')

                async with conn.create_process(term_type=term_type) as process:
                    async def forward_out():
                        try:
                            while True:
                                data = await process.stdout.read(1024)
                                if not data:
                                    break
                                data = osc_escape.sub('', data)
                                data = bracketed_paste.sub('', data)
                                sys.stdout.write(data)
                                sys.stdout.flush()
                        except Exception:
                            pass

                    async def forward_in():
                        loop = asyncio.get_running_loop()
                        try:
                            while True:
                                char = await loop.run_in_executor(None, msvcrt.getch)
                                if char == b'\x03': # Ctrl+C
                                    process.stdin.write('\x03')
                                    continue
                                
                                if char in (b'\x00', b'\xe0'):
                                    # Handle Windows special keys
                                    char2 = await loop.run_in_executor(None, msvcrt.getch)
                                    if char2 == b'H': char = b'\x1b[A' # Up Arrow
                                    elif char2 == b'P': char = b'\x1b[B' # Down Arrow
                                    elif char2 == b'M': char = b'\x1b[C' # Right Arrow
                                    elif char2 == b'K': char = b'\x1b[D' # Left Arrow
                                    elif char2 == b'S': char = b'\x1b[3~' # Delete
                                    else: char = b''
                                
                                if char:
                                    try:
                                        process.stdin.write(char.decode('utf-8'))
                                    except UnicodeDecodeError:
                                        pass
                        except Exception:
                            pass
                    
                    await asyncio.gather(
                        forward_out(), 
                        forward_in()
                    )
            else:
                async with conn.create_process(term_type=term_type, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr) as process:
                    await process.wait()
                
        except Exception as e:
            logger.error(f"Interactive Shell Error on {ip}: {e}")
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

    @classmethod
    async def connect_and_playbook(cls, config: SshHostConfig, playbook: Playbook) -> SshHostResult:
        """
        Resiliently connects to a host via SSH and sequentially executes
        a series of playbook tasks with full Expect engine support.
        """
        ip = config.ip
        port = config.port
        username = config.username
        password = config.password
        timeout = config.timeout_seconds

        start_time = time.perf_counter()
        
        connect_opts = {
            "host": ip,
            "port": port,
            "username": username,
            "password": password,
            "login_timeout": timeout,
        }

        if config.ssh_key:
            connect_opts["client_keys"] = [config.ssh_key]

        if config.ignore_host_keys:
            connect_opts["client_factory"] = TrustingSSHClient
            connect_opts["known_hosts"] = None

        conn = None
        negotiated_kex = None
        negotiated_cipher = None
        used_fallback = False

        try:
            try:
                conn = await asyncssh.connect(**connect_opts)
            except (asyncssh.misc.ProtocolError, asyncssh.misc.DisconnectError) as e:
                if config.auto_negotiate:
                    logger.warning(
                        f"Handshake failed with {ip}:{port} ({e}). Retrying with legacy cryptographic support..."
                    )
                    used_fallback = True
                    legacy_opts = {
                        **connect_opts,
                        "kex_algs": ["diffie-hellman-group1-sha1", "diffie-hellman-group14-sha1", "diffie-hellman-group-exchange-sha1", "diffie-hellman-group-exchange-sha256", "ecdh-sha2-nistp256", "ecdh-sha2-nistp384", "ecdh-sha2-nistp521"],
                        "encryption_algs": ["aes128-cbc", "aes192-cbc", "aes256-cbc", "3des-cbc", "aes128-ctr", "aes192-ctr", "aes256-ctr"],
                        "signature_algs": ["ssh-rsa", "ssh-dss", "ecdsa-sha2-nistp256", "ssh-ed25519"],
                    }
                    conn = await asyncssh.connect(**legacy_opts)
                else:
                    raise e

            negotiated_kex = conn.get_extra_info("kex_alg")
            negotiated_cipher = conn.get_extra_info("cipher_alg")

            full_stdout = ""
            # Sequentially run tasks
            for task in playbook.tasks:
                full_stdout += f"\\n--- TASK: {task.name} ---\\n"
                
                try:
                    # 1. We attempt standard 'exec' channel requests.
                    # This cleanly isolates commands and provides EOF signals.
                    async with conn.create_process(task.command, term_type='vt100') as proc:
                        buf = ""
                        task_timeout = task.timeout or 120 # Default 2 minutes per task
                        
                        while True:
                            # Read in small chunks to process output as fast as possible for the Expect engine
                            try:
                                chunk = await asyncio.wait_for(proc.stdout.read(1024), timeout=task_timeout)
                                if not chunk: # EOF
                                    break
                                buf += chunk
                                full_stdout += chunk
                                
                                if task.expect:
                                    for exp in task.expect:
                                        if re.search(exp.prompt, buf):
                                            proc.stdin.write(exp.send)
                                            buf = "" # Reset buffer after send to avoid repeated matching
                                            break
                            except asyncio.TimeoutError:
                                full_stdout += f"\\n[ERROR: Timeout waiting for task execution after {task_timeout}s]"
                                break

                except asyncssh.misc.ChannelOpenError as coe:
                    # Some legacy/network devices reject 'exec' channels. 
                    # For a robust playbook engine, we log and abort the playbook.
                    full_stdout += f"\\n[ERROR: Host rejected command execution channel. Host might require interactive shell only. {coe}]"
                    raise coe

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            return SshHostResult(
                ip=ip,
                status=SshStatus.SUCCESS,
                stdout=full_stdout.strip(),
                stderr=None,
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
    async def scp_push(cls, config: SshHostConfig, src: str, dest: str) -> SshHostResult:
        """
        Pushes a local file to the remote host using SCP.
        """
        ip = config.ip
        port = config.port
        username = config.username
        password = config.password
        timeout = config.timeout_seconds

        start_time = time.perf_counter()
        
        connect_opts = {
            "host": ip,
            "port": port,
            "username": username,
            "password": password,
            "login_timeout": timeout,
        }

        if config.ssh_key:
            connect_opts["client_keys"] = [config.ssh_key]

        if config.ignore_host_keys:
            connect_opts["client_factory"] = TrustingSSHClient
            connect_opts["known_hosts"] = None

        conn = None
        negotiated_kex = None
        negotiated_cipher = None
        used_fallback = False

        try:
            try:
                conn = await asyncssh.connect(**connect_opts)
            except (asyncssh.misc.ProtocolError, asyncssh.misc.DisconnectError) as e:
                if config.auto_negotiate:
                    logger.warning(
                        f"Handshake failed with {ip}:{port} ({e}). Retrying with legacy cryptographic support..."
                    )
                    used_fallback = True
                    legacy_opts = {
                        **connect_opts,
                        "kex_algs": ["diffie-hellman-group1-sha1", "diffie-hellman-group14-sha1", "diffie-hellman-group-exchange-sha1", "diffie-hellman-group-exchange-sha256", "ecdh-sha2-nistp256", "ecdh-sha2-nistp384", "ecdh-sha2-nistp521"],
                        "encryption_algs": ["aes128-cbc", "aes192-cbc", "aes256-cbc", "3des-cbc", "aes128-ctr", "aes192-ctr", "aes256-ctr"],
                        "signature_algs": ["ssh-rsa", "ssh-dss", "ecdsa-sha2-nistp256", "ssh-ed25519"],
                    }
                    conn = await asyncssh.connect(**legacy_opts)
                else:
                    raise e

            negotiated_kex = conn.get_extra_info("kex_alg")
            negotiated_cipher = conn.get_extra_info("cipher_alg")

            # Execute SCP Push
            await asyncssh.scp(src, (conn, dest))
            
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            return SshHostResult(
                ip=ip,
                status=SshStatus.SUCCESS,
                stdout=f"Successfully pushed {src} to {dest}",
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
    async def scp_pull(cls, config: SshHostConfig, src: str, dest_dir: str) -> SshHostResult:
        """
        Pulls a remote file from the host using SCP, saving it into an IP-segregated subdirectory.
        """
        ip = config.ip
        port = config.port
        username = config.username
        password = config.password
        timeout = config.timeout_seconds

        start_time = time.perf_counter()
        
        connect_opts = {
            "host": ip,
            "port": port,
            "username": username,
            "password": password,
            "login_timeout": timeout,
        }

        if config.ssh_key:
            connect_opts["client_keys"] = [config.ssh_key]

        if config.ignore_host_keys:
            connect_opts["client_factory"] = TrustingSSHClient
            connect_opts["known_hosts"] = None

        conn = None
        negotiated_kex = None
        negotiated_cipher = None
        used_fallback = False

        try:
            try:
                conn = await asyncssh.connect(**connect_opts)
            except (asyncssh.misc.ProtocolError, asyncssh.misc.DisconnectError) as e:
                if config.auto_negotiate:
                    logger.warning(
                        f"Handshake failed with {ip}:{port} ({e}). Retrying with legacy cryptographic support..."
                    )
                    used_fallback = True
                    legacy_opts = {
                        **connect_opts,
                        "kex_algs": ["diffie-hellman-group1-sha1", "diffie-hellman-group14-sha1", "diffie-hellman-group-exchange-sha1", "diffie-hellman-group-exchange-sha256", "ecdh-sha2-nistp256", "ecdh-sha2-nistp384", "ecdh-sha2-nistp521"],
                        "encryption_algs": ["aes128-cbc", "aes192-cbc", "aes256-cbc", "3des-cbc", "aes128-ctr", "aes192-ctr", "aes256-ctr"],
                        "signature_algs": ["ssh-rsa", "ssh-dss", "ecdsa-sha2-nistp256", "ssh-ed25519"],
                    }
                    conn = await asyncssh.connect(**legacy_opts)
                else:
                    raise e

            negotiated_kex = conn.get_extra_info("kex_alg")
            negotiated_cipher = conn.get_extra_info("cipher_alg")

            # Create IP-segregated directory
            target_dir = os.path.join(dest_dir, ip)
            os.makedirs(target_dir, exist_ok=True)
            
            # Use original filename for local destination
            filename = os.path.basename(src)
            local_dest_path = os.path.join(target_dir, filename)

            # Execute SCP Pull
            await asyncssh.scp((conn, src), local_dest_path)
            
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            return SshHostResult(
                ip=ip,
                status=SshStatus.SUCCESS,
                stdout=f"Successfully pulled {src} to {local_dest_path}",
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

class SshRunnerService:
    """
    Orchestrates high-speed, parallel SSH command executions across multiple network hosts.
    Aggregates outcomes and returns a unified execution audit.
    """

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
                results=[],
                executed_at=datetime.now(timezone.utc)
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

        return audit

    async def execute_playbook_concurrently(self, hosts: List[SshHostConfig], playbook: Playbook) -> SshExecutionAudit:
        """
        Concurrently executes a playbook sequence across multiple host configurations.
        """
        if not hosts:
            return SshExecutionAudit(
                command=f"playbook:{playbook.name}",
                targets=[],
                success_count=0,
                failed_count=0,
                results=[],
                executed_at=datetime.now(timezone.utc)
            )

        tasks = [SmartSshClient.connect_and_playbook(cfg, playbook) for cfg in hosts]
        results: List[SshHostResult] = await asyncio.gather(*tasks)

        success_count = sum(1 for res in results if res.status == SshStatus.SUCCESS)
        failed_count = sum(1 for res in results if res.status == SshStatus.FAILED)
        targets = [cfg.ip for cfg in hosts]

        audit = SshExecutionAudit(
            command=f"playbook:{playbook.name}",
            targets=targets,
            success_count=success_count,
            failed_count=failed_count,
            results=results,
            executed_at=datetime.now(timezone.utc)
        )

        return audit

    async def execute_scp_push_concurrently(self, hosts: List[SshHostConfig], src: str, dest: str) -> SshExecutionAudit:
        """
        Concurrently pushes a file to multiple hosts via SCP.
        """
        command_label = f"scp push {src} -> {dest}"
        if not hosts:
            return SshExecutionAudit(
                command=command_label,
                targets=[],
                success_count=0,
                failed_count=0,
                results=[],
                executed_at=datetime.now(timezone.utc)
            )

        tasks = [SmartSshClient.scp_push(cfg, src, dest) for cfg in hosts]
        results: List[SshHostResult] = await asyncio.gather(*tasks)

        success_count = sum(1 for res in results if res.status == SshStatus.SUCCESS)
        failed_count = sum(1 for res in results if res.status == SshStatus.FAILED)
        targets = [cfg.ip for cfg in hosts]

        audit = SshExecutionAudit(
            command=command_label,
            targets=targets,
            success_count=success_count,
            failed_count=failed_count,
            results=results,
            executed_at=datetime.now(timezone.utc)
        )

        return audit

    async def execute_scp_pull_concurrently(self, hosts: List[SshHostConfig], src: str, dest_dir: str) -> SshExecutionAudit:
        """
        Concurrently pulls a file from multiple hosts via SCP into IP-segregated folders.
        """
        command_label = f"scp pull {src} -> {dest_dir}"
        if not hosts:
            return SshExecutionAudit(
                command=command_label,
                targets=[],
                success_count=0,
                failed_count=0,
                results=[],
                executed_at=datetime.now(timezone.utc)
            )

        tasks = [SmartSshClient.scp_pull(cfg, src, dest_dir) for cfg in hosts]
        results: List[SshHostResult] = await asyncio.gather(*tasks)

        success_count = sum(1 for res in results if res.status == SshStatus.SUCCESS)
        failed_count = sum(1 for res in results if res.status == SshStatus.FAILED)
        targets = [cfg.ip for cfg in hosts]

        audit = SshExecutionAudit(
            command=command_label,
            targets=targets,
            success_count=success_count,
            failed_count=failed_count,
            results=results,
            executed_at=datetime.now(timezone.utc)
        )

        return audit

    async def interactive_shell(self, config: SshHostConfig, term_type: str = "xterm-256color") -> None:
        """
        Opens a fully interactive SSH shell natively over the terminal.
        """
        client = SmartSshClient()
        await client.connect_and_shell(config, term_type=term_type)

