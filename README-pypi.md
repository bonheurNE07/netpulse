<div align="center">
  <h1>NetPulse</h1>
  <p>High-performance network discovery and analysis suite combining Rust's raw-socket speed with a Python/FastAPI orchestration layer.</p>

  <p>
    <a href="https://pypi.org/project/netpulse/"><img src="https://img.shields.io/pypi/v/netpulse.svg?style=flat-square" alt="PyPI version" /></a>
    <a href="https://pypi.org/project/netpulse/"><img src="https://img.shields.io/pypi/pyversions/netpulse.svg?style=flat-square" alt="Python Versions" /></a>
    <a href="https://github.com/bendeze/netpulse/blob/main/LICENSE"><img src="https://img.shields.io/github/license/bendeze/netpulse?style=flat-square" alt="License" /></a>
  </p>
</div>

---

## Overview

**NetPulse** is an enterprise-grade network discovery and analysis platform designed to streamline infrastructure auditing and subnet management. It acts as both a premium CLI tool and a secure REST API.

By decoupling the systems execution layer into a compiled Rust extension (`pnet`, `socket2`), NetPulse achieves wire-speed performance for Layer 2 (ARP) and Layer 3 (ICMP) sweeps, while exposing a flexible, Pydantic-powered Python interface.

## Key Features

- **High-Speed Discovery**: Sub-second execution of wide-scale network sweeps.
- **Advanced Subnet Engine**: A robust calculator supporting bitwise alignment, FLSM partitioning, and Variable-Length Subnet Masking (VLSM) allocations.
- **Drift Detection**: Automated comparisons of current network states against historical baselines stored locally.
- **ProxyJump / Bastion Support**: Execute concurrent SSH commands across hundreds of targets by multiplexing through a single DMZ tunnel.
- **Zero-Privilege Mock Fallback**: A simulated engine allowing developers to test UI and API endpoints locally without requiring root Linux network capabilities.

---

## Installation

Install directly from PyPI:

```bash
pip install netpulse
```

*Note: For actual physical network discovery, the Python binary requires elevated raw socket capabilities (`cap_net_raw`) or superuser privileges.*

---

## Quick Start (CLI)

```bash
# Standard interactive table sweep (requires root or setcap permissions)
sudo netpulse discover 172.19.57.0/24

# Subnet bitwise alignment calculator
netpulse subnet info 192.168.1.50/24

# Perform VLSM allocation for varying departmental size requirements
netpulse subnet vlsm 192.168.1.0/24 --req "HR=120,Dev=50,Sales=20,Links=2"
```

## Documentation

For full instructions, architectural details, and REST API setup, please visit the [Official GitHub Repository](https://github.com/bendeze/netpulse).
