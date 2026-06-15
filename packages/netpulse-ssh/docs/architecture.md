# Architecture

The `netpulse-ssh` package is architected to perform massively concurrent, non-blocking SSH executions across networking infrastructure.

## Component Flow & 3-Tier Architecture

To guarantee high scalability and clean separation of concerns, `netpulse-ssh` is organized into a strict three-tier architecture:

### 1. Presentation & Interface Layer
- **`netpulse.ssh.cli`**: A robust `Typer`-based CLI interface that translates shell arguments into domain models and renders execution audits into rich, colorized terminal tables.
- **`netpulse.ssh.api`**: A stateless `FastAPI` REST router designed to be easily mounted into larger web dashboards. *(Note: Because REST is stateless, it only exposes the concurrent mass-execution endpoints, not the interactive PTY shell).*

### 2. Orchestration Layer
- **`netpulse.ssh.runner.SshRunnerService`**: The core execution engine. 
  - **Mass Execution**: Utilizes `asyncio.gather` to launch parallel, non-blocking asynchronous routines for every target device, collating outputs and latencies into a structured `SshExecutionAudit` domain model.
  - **Interactive Shell**: Instantiates and orchestrates the custom Pure Python PTY Emulator, mapping standard input and output streams asynchronously.

### 3. Protocol & Persistence Layer
- **`netpulse.ssh.runner.SmartSshClient`**: The lowest-level connection wrapper built on top of `asyncssh`.
  - **Legacy Equipment Healing**: Automatically detects strict OpenSSH cipher drops and dynamically restarts the handshake using legacy algorithms (e.g., `diffie-hellman-group1-sha1`, `3des-cbc`) specifically tailored for older Cisco and Juniper gear.
  - **Pagination Bypass**: Pre-emptively injects `terminal length 0` to disable pagination before executing mass commands.
  - **Cross-Platform PTY Engine**: Handles complex byte-stream manipulation and raw keystroke capture (via `msvcrt` on Windows or `termios` on Unix) to provide a completely native terminal experience entirely within Python.
