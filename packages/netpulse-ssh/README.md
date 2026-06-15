<h1 align="center">NetPulse SSH</h1>

<p align="center">
  <em>High-performance, standalone Python library & CLI for concurrent SSH command execution across network devices.</em>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/bonheurNE07/netpulse/main/packages/netpulse-ssh/docs/assets/netpulse_ssh_logo.png" alt="NetPulse SSH Logo" width="250"/>
</p>

<p align="center">
  <a href="https://pypi.org/project/netpulse-ssh/"><img src="https://img.shields.io/pypi/v/netpulse-ssh?color=magenta&label=pypi%20package" alt="PyPI version"></a>
  <a href="https://pypi.org/project/netpulse-ssh/"><img src="https://img.shields.io/pypi/pyversions/netpulse-ssh" alt="Python Versions"></a>
  <a href="https://github.com/bonheurNE07/netpulse/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/bonheurNE07/netpulse"><img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black"></a>
</p>

---

**`netpulse-ssh`** is an ultra-fast, resilient SSH execution engine extracted from the [NetPulse](https://github.com/bonheurNE07/netpulse) discovery suite. It allows network engineers and automation pipelines to execute commands across hundreds of network devices simultaneously, without blocking I/O or crashing due to a single offline host.

## ✨ Features

- **Massive Concurrency**: Scales horizontally using `asyncio` to execute commands across hundreds of targets simultaneously.
- **Legacy Equipment Healing**: Automatically detects strict OpenSSH cipher drops and seamlessly falls back to legacy algorithms (e.g., `diffie-hellman-group1-sha1`, `3des-cbc`) which are frequently required for older Cisco or Juniper gear.
- **Smart Privilege Escalation**: Natively supports Cisco `enable` mode privilege escalation without breaking automation.
- **Pagination Suppression**: Automatically injects `terminal length 0` before command execution to bypass interactive `--More--` prompts.
- **REST API Enabled**: Run the built-in FastAPI uvicorn wrapper to serve concurrent execution logic dynamically to web dashboards or automation scripts.

## 🚀 Quickstart

### Installation

Install globally or locally via `pip`:

```bash
pip install netpulse-ssh
```

### CLI Usage

**Concurrent Execution**
Execute a command across multiple devices concurrently and get a beautiful, structured table summary:

```bash
netpulse-ssh execute 192.168.1.5 10.0.0.1 -c "show ip interface brief" -u admin -p password
```

**Interactive Shell**
Drop directly into a live interactive SSH shell to manually configure a specific target:

```bash
netpulse-ssh shell 192.168.1.5 -u admin -p password
```
*(If you omit `-u` or `-p`, the CLI will securely prompt you for them!)*

### Python API Integration

Use our cleanly typed Pydantic models and logic natively inside your own tools. The runner is completely agnostic and returns an audit object containing stdout/stderr per host:

```python
import asyncio
from netpulse.ssh.models import SshHostConfig
from netpulse.ssh.runner import SshRunnerService

async def main():
    hosts = [
        SshHostConfig(ip="192.168.1.1", username="admin", password="password"),
        SshHostConfig(ip="10.0.0.1", username="admin", password="password"),
    ]
    
    runner = SshRunnerService()
    audit = await runner.execute_concurrently(hosts, "show version")
    
    for result in audit.results:
        print(f"Host {result.ip} status: {result.status}")
        print(result.stdout)

if __name__ == "__main__":
    asyncio.run(main())
```

## 📖 Documentation

Detailed documentation is available in the `docs/` directory:
- 🗺️ [**Usage Guide**](docs/usage.md) - Deep dive into CLI and REST API examples.
- 🏗️ [**Architecture**](docs/architecture.md) - Understand the asynchronous execution engine and legacy fallbacks.
- 🧠 [**Design Decisions**](docs/design.md) - Read about the decoupled persistence approach.
- 🧪 [**Contributing**](docs/contributing.md) - The development onboarding guide.

## 🤝 Contributing

We welcome contributions from the community! `netpulse-ssh` is open-source and maintained actively. 
Please read our [**Contributing Guidelines**](docs/contributing.md) to understand how to clone the repository and submit your Pull Requests. 

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.
