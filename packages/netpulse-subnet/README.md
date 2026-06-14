<p align="center">
  <img src="https://github.com/bonheurNE07/netpulse/blob/4187e7ea267acea4395eed04e141916fe4cfa322/packages/netpulse-subnet/docs/assets/logo-removebg-preview.png" alt="NetPulse Subnet Logo" width="250"/>
</p>

<h1 align="center">NetPulse Subnet</h1>

<p align="center">
  <em>High-performance, standalone Python library & CLI for IPv4 network calculations, FLSM splitting, and VLSM allocation.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/netpulse-subnet/"><img src="https://img.shields.io/pypi/v/netpulse-subnet?color=007ec6&label=pypi%20package" alt="PyPI version"></a>
  <a href="https://pypi.org/project/netpulse-subnet/"><img src="https://img.shields.io/pypi/pyversions/netpulse-subnet" alt="Python Versions"></a>
  <a href="https://github.com/bonheurNE07/netpulse/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/bonheurNE07/netpulse"><img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black"></a>
</p>

---

**`netpulse-subnet`** is a standalone network administration tool extracted from the larger [NetPulse](https://github.com/bonheurNE07/netpulse) discovery suite. It is built to help network engineers programmatically calculate, partition, and optimize IPv4 address spaces natively in Python or directly from the terminal.

## ✨ Features

- **Subnet Calculator (`info`)**: Deep visibility into IP boundaries, subnet masks, wildcard masks, and bitwise binary representation.
- **Fixed-Length Subnet Splitter (`split`)**: Flawlessly chunk large network blocks (FLSM) based on exact host requirements or target partition counts.
- **Variable-Length Planner (`vlsm`)**: Eliminate IP wastage. Pass an array of varying host requirements and mathematically sort them into the tightest fitting CIDR blocks dynamically.
- **Namespace Packaging**: Fully decoupled from `netpulse-core`. It functions as a lightweight script with minimal dependencies (only `pydantic`, `typer`, and `fastapi`).
- **REST API Enabled**: Run the built-in FastAPI uvicorn wrapper to serve subnet calculation logic dynamically to web dashboards or automation scripts.

## 🚀 Quickstart

### Installation

Install globally or locally via `pip`:

```bash
pip install netpulse-subnet
```

### CLI Usage

```bash
# Calculate detailed subnet boundaries for an IP
netpulse-subnet info 192.168.1.50/24

# Split a class A network into equal /10 blocks
netpulse-subnet split 10.0.0.0/8 --subnets 4

# Optimize and allocate VLSM blocks from a /24 parent network
netpulse-subnet vlsm 192.168.1.0/24 --req "HR=120,Dev=50,Sales=20,Guest=10"
```

### Python API Integration

Use our cleanly typed Pydantic models and logic natively inside your own tools:

```python
from netpulse.subnet.services.subnet import calculate_subnet_info, allocate_vlsm

# Retrieve detailed boundary models
info = calculate_subnet_info("192.168.1.50", "24")
print(f"Broadcast IP: {info.broadcast_address}")

# Plan VLSM allocation
result = allocate_vlsm("192.168.1.0/24", [{"name": "HR", "hosts": 120}])
print(f"Allocated block: {result.allocations[0].network_cidr}")
```

## 📖 Documentation

For in-depth explanations, architectural decisions, and integration examples, dive into the documentation:

* 🗺️ [**Usage Guide**](docs/usage.md) - Deep dive into CLI and REST API examples.
* 🐍 [**API Reference**](docs/api_reference.md) - Documentation for the Python service layer and Pydantic models.
* 🧠 [**Design & Algorithms**](docs/design.md) - Read about the mathematical algorithms behind our FLSM and VLSM operations.
* 🏗️ [**Architecture**](docs/architecture.md) - Understand the strict separation of concerns and `netpulse` implicit namespace.
* 🧪 [**Testing**](docs/testing.md) - Learn how to run our comprehensive test suite.

## 🤝 Contributing

We welcome contributions from the community! `netpulse-subnet` is open-source and maintained actively. 

Please read our [**Contributing Guidelines**](docs/contributing.md) to understand how to clone the repository, use `uv` for dependency management, and submit your Pull Requests. 

If you've found a bug or have a feature request, feel free to open an issue!

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.
