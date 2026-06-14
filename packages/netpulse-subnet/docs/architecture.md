# Architecture

The `netpulse-subnet` package is designed as a standalone, zero-dependency (excluding Pydantic/FastAPI wrappers) sub-module of the larger NetPulse ecosystem. It handles complex IPv4 subnet mathematical operations like Fixed-Length Subnet Masking (FLSM) and Variable-Length Subnet Masking (VLSM).

## System Boundaries

The package is partitioned into three main layers:

1. **Models Layer (`netpulse.subnet.models`)**:
   Contains pure Pydantic dataclasses (`SubnetInfo`, `VLSMResult`, `VLSMAllocation`) that dictate the data structures for network boundaries, IP addresses, and CIDR notation. These models enforce strict type validation at runtime.

2. **Services Layer (`netpulse.subnet.services`)**:
   Contains the pure business logic and algorithms. The core functions (`calculate_subnet_info`, `allocate_vlsm`, `split_fixed_length`) do not know about the CLI or API. They strictly accept and return Pydantic objects or native Python types.

3. **Presentation Layer (`netpulse.subnet.cli` & `netpulse.subnet.api`)**:
   The top-most layer that exposes the services to the outside world.
   - **CLI**: Uses `Typer` and `Rich` to render the outputs as beautiful terminal tables.
   - **API**: Uses `FastAPI` to expose the exact same services as RESTful JSON endpoints.

## Ecosystem Integration (Namespace Packaging)

This package is structured as a **PEP 420 Implicit Namespace Package** under `netpulse.subnet`. This allows `netpulse-subnet` to be installed entirely independently via PyPI (`pip install netpulse-subnet`), but when installed alongside `netpulse-core` or `netpulse-engine`, they all share the exact same top-level `netpulse` import path transparently.
