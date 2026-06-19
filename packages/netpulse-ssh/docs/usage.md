# NetPulse SSH Usage

The `netpulse-ssh` package can be utilized as a standalone Command Line Interface (CLI), an independent REST API, or seamlessly imported as a standard Python library into your custom scripts.

## Standalone CLI

To execute a command across multiple devices concurrently:
```bash
netpulse-ssh execute 192.168.1.5 10.0.0.1 -c "show ip interface brief" -u admin -p password
```

To drop into a live interactive SSH shell to manually configure a specific target:
```bash
netpulse-ssh shell 192.168.1.5 -u admin -p password
```

To natively push a file to multiple remote hosts concurrently using SCP:
```bash
netpulse-ssh scp push 192.168.1.5 10.0.0.1 --src local.bin --dest /flash/ -u admin -p password
```

To natively pull a remote file from multiple hosts, automatically organizing them into IP-segregated folders (e.g., `./backups/192.168.1.5/nginx.conf`):
```bash
netpulse-ssh scp pull 192.168.1.5 10.0.0.1 --src /etc/nginx/nginx.conf --dest ./backups/ -u admin -p password
```

Options:
- `-c, --command`: The SSH command to execute (for `execute`).
- `-u, --user`: The SSH login username.
- `-p, --pass`: The SSH password.
- `-e, --enable`: A privilege execution mode password (e.g., Cisco `enable`).
- `--port`: The SSH port (default `22`).

## Standalone API

You can boot up a standalone FastAPI server containing only the SSH router:

```python
import uvicorn
from fastapi import FastAPI
from netpulse.ssh.api import ssh_router

app = FastAPI()
app.include_router(ssh_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

**Endpoint:** `POST /api/v1/ssh/execute`
```json
{
  "hosts": [
    {
      "ip": "192.168.1.1",
      "port": 22
    }
  ],
  "command": "show version",
  "username": "admin",
  "password": "secret_password"
}
```

**Important Note on Interactive Shells via REST:** Because the `shell` command requires a persistent, two-way bidirectional byte stream (Pseudo-Terminal), it cannot be exposed over a standard stateless REST API. If you are building a web UI for the interactive shell, you must integrate the Python library directly into a WebSockets backend.

## Python Library Integration

`netpulse-ssh` was designed from the ground up to be seamlessly imported into your custom Python backends or orchestration scripts.

### 1. Mass Concurrent Execution
```python
import asyncio
from netpulse.ssh.models import SshHostConfig
from netpulse.ssh.runner import SshRunnerService

async def mass_execute():
    hosts = [
        SshHostConfig(ip="10.0.0.1", username="admin", password="password"),
        SshHostConfig(ip="192.168.1.5", username="admin", password="password"),
    ]
    
    runner = SshRunnerService()
    # Runs non-blocking across all hosts simultaneously
    audit = await runner.execute_concurrently(hosts, "show version")
    
    for result in audit.results:
        print(f"[{result.ip}] Status: {result.status} | Latency: {result.latency_ms}ms")
        print(result.stdout)

if __name__ == "__main__":
    asyncio.run(mass_execute())
```

### 2. Embedding the Pure Python PTY Interactive Shell
You can use our highly resilient, pure-Python PTY emulator directly in your scripts. This will instantly bind the current process's standard input/output to the remote SSH tunnel, complete with native keystroke capturing, auto-completion, and arrow-key history navigation.

```python
import asyncio
from netpulse.ssh.models import SshHostConfig
from netpulse.ssh.runner import SshRunnerService

async def start_pty_shell():
    config = SshHostConfig(
        ip="10.0.0.1",
        username="admin", 
        password="secret_password" # Auto-login avoids prompts!
    )
    
    runner = SshRunnerService()
    # This will block and take over the terminal until the user types 'exit'
    await runner.interactive_shell(config, term_type="xterm-256color")

if __name__ == "__main__":
    asyncio.run(start_pty_shell())
```
