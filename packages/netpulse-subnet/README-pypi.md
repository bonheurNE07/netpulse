<div align="center">
  <img src="https://raw.githubusercontent.com/bendeze/netpulse/main/packages/netpulse-subnet/docs/assets/logo-removebg-preview.png" alt="NetPulse Subnet Logo" width="250"/>

  <h1>NetPulse Subnet</h1>
  <p>High-performance, standalone Python library & CLI for IPv4 & IPv6 network calculations, FLSM splitting, and VLSM allocation.</p>

  <p>
    <a href="https://pypi.org/project/netpulse-subnet/"><img src="https://img.shields.io/pypi/v/netpulse-subnet.svg?style=flat-square" alt="PyPI version" /></a>
    <a href="https://pypi.org/project/netpulse-subnet/"><img src="https://img.shields.io/pypi/pyversions/netpulse-subnet.svg?style=flat-square" alt="Python Versions" /></a>
    <a href="https://github.com/bendeze/netpulse/blob/main/LICENSE"><img src="https://img.shields.io/github/license/bendeze/netpulse?style=flat-square" alt="License" /></a>
  </p>
</div>

---

## Overview

**`netpulse-subnet`** is a standalone network administration tool extracted from the larger [NetPulse](https://github.com/bendeze/netpulse) discovery suite. It helps network engineers programmatically calculate, partition, and optimize IPv4 and IPv6 address spaces natively in Python or directly from the terminal.

## Key Features

- **Dual-Stack Support**: Robust handling of both IPv4 and 128-bit IPv6 subnets.
- **Subnet Calculator (`info`)**: Deep visibility into IP boundaries, subnet masks, wildcard masks, and binary representation.
- **Fixed-Length Subnet Splitter (`split`)**: Flawlessly chunk large network blocks based on exact host requirements or target partition counts.
- **Variable-Length Planner (`vlsm`)**: Mathematically sort varying host requirements into the tightest fitting CIDR blocks dynamically to eliminate IP wastage.
- **Conflict Detection (`validate`)**: Ingest massive lists of legacy subnets and instantly detect routing clashes using a high-speed O(N log N) line-sweep algorithm.
- **REST API Enabled**: Run the built-in FastAPI uvicorn wrapper to serve subnet calculation logic dynamically to web dashboards or automation scripts.

---

## Installation

Install globally or locally via `pip`:

```bash
pip install netpulse-subnet
```

---

## Quick Start (CLI)

```bash
# Calculate detailed subnet boundaries for an IP
netpulse-subnet info 192.168.1.50/24

# Optimize and allocate VLSM blocks from a /24 parent network
netpulse-subnet vlsm 192.168.1.0/24 --req "HR=120,Dev=50,Sales=20,Guest=10"

# Validate a list of subnets to ensure no overlap, and calculate free space
netpulse-subnet validate 192.168.1.0/24 192.168.1.128/25 --parent 192.168.1.0/23
```

## Python Integration

Use cleanly typed Pydantic models natively inside your own tools:

```python
from netpulse.subnet.services.subnet import calculate_subnet_info, validate_subnets

# Retrieve detailed boundary models
info = calculate_subnet_info("192.168.1.50", "24")
print(f"Broadcast IP: {info.broadcast_address}")

# Validate for overlaps and free space
valid = validate_subnets(["10.0.0.0/24", "10.0.1.0/24"], parent_network="10.0.0.0/22")
print(f"Conflicts: {valid.has_overlaps}")
```

## Documentation

For full API references, algorithms, and documentation, visit the [Official GitHub Repository](https://github.com/bendeze/netpulse/tree/main/packages/netpulse-subnet).
