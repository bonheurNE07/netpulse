# Usage Guide

`netpulse-discovery` can be used via its standalone CLI, its standalone REST API, or programmatically as a Python library.

> [!WARNING]
> Because `netpulse-discovery` utilizes raw sockets to generate ICMP and ARP packets, the tool must either be run with elevated privileges (e.g., `sudo`) or run in Mock Mode.

## Mock Mode (Development)
If you do not have root access or want to test safely, enable mock mode:
```bash
export NETPULSE_MOCK=1
```

## 1. Standalone CLI
> [!IMPORTANT]
> **Multiplatform Execution Requirements:**
> - **Linux / macOS:** You must prefix your commands with `sudo` to grant raw socket permissions.
> - **Windows:** You must run your commands inside an **Administrator Command Prompt** or Administrator PowerShell session.

Run a basic network scan directly from the terminal:

```bash
# Linux / macOS
sudo netpulse-discovery scan 192.168.1.0/24

# Windows (Run in Admin Prompt)
netpulse-discovery scan 192.168.1.0/24
```

### Exporting Results

You can export the discovery scan directly to a file format of your choice (`.json`, `.yaml`, or `.txt`):

```bash
# Example for Linux/macOS
sudo netpulse-discovery scan 192.168.1.0/24 --output scan_report.json
```

### Stateless Drift Analysis

You can compute topological network drift locally by supplying two JSON scan exports. This command does not require elevated privileges since it only parses files:

```bash
netpulse-discovery drift old_scan.json new_scan.json --output drift_report.yaml
```

### Standalone API Server

To spin up a standalone REST API microservice:

```bash
netpulse-discovery serve --host 127.0.0.1 --port 8000
```
You can then POST to:
- `http://127.0.0.1:8000/discovery/scan` with payload `{"target": "192.168.1.0/24"}`
- `http://127.0.0.1:8000/discovery/drift/compare` with payload `{"scan_old": {...}, "scan_new": {...}}`
- `http://127.0.0.1:8000/discovery/drift/scan` with payload `{"target": "192.168.1.0/24", "scan_old": {...}}`

This returns a raw, structured JSON output containing the discovered devices, their MAC addresses, vendors, and RTT (Round Trip Time).

## 2. Python Library
Import the services to embed discovery directly into your application:

```python
import asyncio
from netpulse.discovery.services.discovery import DiscoveryService
from netpulse.discovery.models.discovery import DiscoveryMethod

async def main():
    service = DiscoveryService()
    result = await service.discover_network(
        "10.0.0.0/24", 
        methods=[DiscoveryMethod.ARP]
    )
    
    for device in result.devices:
        print(f"Found {device.ip} ({device.mac}) - Vendor: {device.vendor}")

asyncio.run(main())
```

## 3. Standalone API
To run the decoupled REST API for microservice integration:

```bash
# Mount the router to a FastAPI app and run it with uvicorn
sudo uv run uvicorn netpulse.discovery.api:discovery_router
```
