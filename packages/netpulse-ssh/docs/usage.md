# NetPulse SSH Usage

The `netpulse-ssh` package can be utilized as a standalone Command Line Interface (CLI), an independent REST API, or seamlessly imported as a standard Python library into your custom scripts.

## Standalone CLI

To execute a command across multiple devices concurrently:
```bash
netpulse-ssh execute 192.168.1.5 10.0.0.1 -c "show ip interface brief" -u admin -p password
```

Options:
- `-c, --command`: The SSH command to execute.
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

## Python Library

```python
import asyncio
from netpulse.ssh.models import SshHostConfig
from netpulse.ssh.runner import SshRunnerService

async def run():
    hosts = [
        SshHostConfig(ip="10.0.0.1", username="admin", password="password")
    ]
    runner = SshRunnerService()
    audit = await runner.execute_concurrently(hosts, "show version")
    print(audit.results[0].stdout)

asyncio.run(run())
```
