# NetPulse Discovery Architecture

The `netpulse-discovery` package employs a hybrid architectural design, leveraging both Python and Rust to achieve high-performance network mapping while maintaining the flexibility of Python APIs.

## Core Components

### 1. `netpulse-rust` Core
At the lowest level, all blocking, packet-level network I/O is performed by a compiled Rust binary. This bypasses Python's Global Interpreter Lock (GIL) and provides near wire-speed packet generation for ARP and ICMP sweeps.
- **ARP Sweeps:** Uses `libpcap` to broadcast ARP requests rapidly across the local link.
- **ICMP Sweeps:** Uses raw sockets to ping targets.

### 2. The Python Engine (`netpulse.discovery.engine`)
This layer acts as the FFI (Foreign Function Interface) boundary. It imports the compiled Rust extension and exposes it to the higher-level Python services.

### 3. Asynchronous Services (`netpulse.discovery.services`)
- **DiscoveryService**: The primary orchestrator. It executes the Rust engine via `asyncio.to_thread` to ensure that Python's async event loop is never blocked by raw socket waits. It then enriches the raw results with MAC vendor lookups and port scans.
- **PortScannerService**: A purely native-Python TCP connect scanner using `asyncio` streams.
- **DriftService**: Implements state-aware logic to compare current discovery results against historical baselines, allowing for accurate mapping of network topological changes over time.

### 4. Pydantic Domain Models (`netpulse.discovery.models`)
The data contract layer. Raw byte responses from the network are parsed, validated, and normalized into `DiscoveryResult` and `Device` models before being returned to the user or downstream consumers.
