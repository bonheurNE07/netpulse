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
Run a basic network scan directly from the terminal:

```bash
# Scan a local /24 subnet
sudo uv run netpulse-discovery scan 192.168.1.0/24 --timeout 500
```
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
