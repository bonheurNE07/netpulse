<p align="center">
  <img src="https://raw.githubusercontent.com/bonheurNE07/netpulse/main/packages/netpulse-subnet/docs/assets/logo-removebg-preview.png" alt="NetPulse Subnet Logo" width="250"/>
</p>

<h1 align="center">NetPulse Subnet</h1>

<p align="center">
  <em>High-performance, standalone Python library & CLI for IPv4 & IPv6 network calculations, FLSM splitting, and VLSM allocation.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/netpulse-subnet/"><img src="https://img.shields.io/pypi/v/netpulse-subnet?color=007ec6&label=pypi%20package" alt="PyPI version"></a>
  <a href="https://pypi.org/project/netpulse-subnet/"><img src="https://img.shields.io/pypi/pyversions/netpulse-subnet" alt="Python Versions"></a>
  <a href="https://github.com/bonheurNE07/netpulse/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/bonheurNE07/netpulse"><img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black"></a>
</p>

---

**`netpulse-subnet`** is a standalone network administration tool extracted from the larger [NetPulse](https://github.com/bonheurNE07/netpulse) discovery suite. It is built to help network engineers programmatically calculate, partition, and optimize IPv4 and IPv6 address spaces natively in Python or directly from the terminal.

## ✨ Features

- **Dual-Stack Support (IPv4 & IPv6)**: The mathematical engine dynamically routes calculation requests to support huge 128-bit subnets securely with memory exhaustion safeguards.
- **Subnet Calculator (`info`)**: Deep visibility into IP boundaries, subnet masks, wildcard masks, and bitwise binary representation.
- **Fixed-Length Subnet Splitter (`split`)**: Flawlessly chunk large network blocks (FLSM) based on exact host requirements or target partition counts.
- **Variable-Length Planner (`vlsm`)**: Eliminate IP wastage. Pass an array of varying host requirements and mathematically sort them into the tightest fitting CIDR blocks dynamically.
- **Overlap & Conflict Detection (`validate`)**: Ingest massive lists of legacy subnets and instantly detect routing clashes using a high-speed O(N log N) line-sweep algorithm, while simultaneously calculating available free space within a parent block.
- **Route Summarization (`summarize`)**: Merge multiple discontiguous subnets into the tightest encompassing supernet. The tool warns about any routing "slack" space generated.
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

# Validate a list of subnets to ensure no overlap, and calculate free space
netpulse-subnet validate 192.168.1.0/24 192.168.1.128/25 --parent 192.168.1.0/23

# Summarize multiple networks into a supernet block
netpulse-subnet summarize 192.168.0.0/24 192.168.1.0/24 192.168.2.0/24 192.168.3.0/24
```

### Python API Integration

Use our cleanly typed Pydantic models and logic natively inside your own tools:

```python
from netpulse.subnet.services.subnet import calculate_subnet_info, allocate_vlsm, validate_subnets

# Retrieve detailed boundary models
info = calculate_subnet_info("192.168.1.50", "24")
print(f"Broadcast IP: {info.broadcast_address}")

# Validate for overlaps and free space
valid = validate_subnets(["10.0.0.0/24", "10.0.1.0/24"], parent_network="10.0.0.0/22")
print(f"Conflicts: {valid.has_overlaps}")
print(f"First free block: {valid.free_space[0]}")
```

## 📖 Documentation

For in-depth explanations, architectural decisions, and integration examples, dive into the documentation:

* 🗺️ [**Usage Guide**](docs/usage.md) - Deep dive into CLI and REST API examples.
* 🐍 [**API Reference**](docs/api_reference.md) - Documentation for the Python service layer and Pydantic models.
* 🧠 [**Design & Algorithms**](docs/design.md) - Read about the mathematical algorithms behind our FLSM and VLSM operations.
* ⚡ [**Validation Engine**](docs/validation_engine.md) - Deep dive into the O(N log N) Line-Sweep overlap detection engine.
* 🏗️ [**Architecture**](docs/architecture.md) - Understand the strict separation of concerns and `netpulse` implicit namespace.
* 🧪 [**Testing**](docs/testing.md) - Learn how to run our comprehensive test suite.

## 🤝 Contributing

We welcome contributions from the community! `netpulse-subnet` is open-source and maintained actively. 

Please read our [**Contributing Guidelines**](docs/contributing.md) to understand how to clone the repository, use `uv` for dependency management, and submit your Pull Requests. 

If you've found a bug or have a feature request, feel free to open an issue!

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.
