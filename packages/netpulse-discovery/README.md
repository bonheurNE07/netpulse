<p align="center">
  <img src="docs/assets/logo.png" alt="NetPulse Discovery Logo" width="300"/>
</p>

# NetPulse Discovery

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![Rust](https://img.shields.io/badge/Powered%20by-Rust-orange?logo=rust&logoColor=white)](https://rust-lang.org)
[![Build Status](https://img.shields.io/badge/Build-Passing-brightgreen?logo=github)](https://github.com/bonheur/netpulse)

**NetPulse Discovery** is a high-performance, asynchronous network mapping and drift-analysis engine. By offloading packet-level networking to a compiled Rust core, it achieves near wire-speed execution while maintaining a flexible, developer-friendly Python API.

## 🚀 Key Features

- **Blazing Fast Scans:** Leverages `libpcap` and raw sockets in Rust to execute ARP and ICMP sweeps orders of magnitude faster than standard Python libraries.
- **Asynchronous Port Scanning:** Native `asyncio` TCP connect scanner that can check hundreds of ports across multiple devices concurrently.
- **Drift Detection:** Built-in intelligence to compare historical scans and calculate exact topological drift (e.g., "Host 192.168.1.5 went offline").
- **MAC Vendor Resolution:** Automatically translates hardware MAC addresses into human-readable manufacturer names.
- **Standalone API & CLI:** Usable as a Python library, a Typer-powered CLI, or a FastAPI REST microservice.

## 📦 Installation

Since NetPulse Discovery is part of the NetPulse workspace, it relies on `uv` for dependency management and workspace resolution.

```bash
uv sync
```

## ⚡ Quickstart

### As a CLI Tool

The standalone CLI returns structured JSON output perfect for piping into `jq` or other tools.

```bash
# Note: Raw sockets require elevated privileges
sudo uv run netpulse-discovery scan 192.168.1.0/24 --timeout 500
```

### As a Python Library

Embed the high-performance engine directly into your own applications:

```python
import asyncio
from netpulse.discovery.services.discovery import DiscoveryService
from netpulse.discovery.models.discovery import DiscoveryMethod

async def main():
    service = DiscoveryService()
    # Scans the network using ARP resolution
    result = await service.discover_network(
        "10.0.0.0/24", 
        methods=[DiscoveryMethod.ARP]
    )
    
    for device in result.devices:
        print(f"[{device.ip}] {device.mac} - {device.vendor}")

asyncio.run(main())
```

## 📚 Documentation

For more detailed guides, check out the `docs/` folder:
- [Usage Guide](docs/usage.md)
- [Architecture Overview](docs/architecture.md)
- [Contributing Guidelines](docs/contributing.md)
