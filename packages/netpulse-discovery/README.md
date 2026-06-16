<p align="center">
  <img src="https://raw.githubusercontent.com/bonheurNE07/netpulse/main/packages/netpulse-discovery/docs/assets/logo.png" alt="NetPulse Discovery Logo" width="300"/>
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

NetPulse Discovery is distributed as a pre-compiled binary wheel. It is entirely self-sufficient and requires no Rust compiler or external dependencies to install!

```bash
pip install netpulse-discovery
```

## ⚡ Quickstart

### As a CLI Tool
The standalone CLI returns structured JSON output perfect for piping into `jq` or other tools. You can also export directly to files!

> [!IMPORTANT]
> **Multiplatform Execution:** Low-level network scanning requires elevated privileges.
> - **Linux / macOS:** Prefix your commands with `sudo`
> - **Windows:** Open an **Administrator Command Prompt** or PowerShell session to execute.

```bash
# Scan a network
sudo netpulse-discovery scan 192.168.1.0/24 --timeout 500

# Export results directly to a file
sudo netpulse-discovery scan 192.168.1.0/24 --output results.json
sudo netpulse-discovery scan 192.168.1.0/24 --output results.yaml
sudo netpulse-discovery scan 192.168.1.0/24 --output results.txt

# Calculate Network Drift from two exported JSON files (No sudo required)
netpulse-discovery drift old_results.json results.json --output drift_report.yaml
```

### As a Standalone REST API
You can spin up a dedicated, hyper-fast FastAPI server instantly:

```bash
netpulse-discovery serve --port 8000
```
Then send requests to `http://localhost:8000/discovery/scan` or `http://localhost:8000/discovery/drift/compare`.

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
