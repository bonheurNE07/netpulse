# Contributing to NetPulse Discovery

Welcome! We appreciate your interest in contributing to the NetPulse suite. Because `netpulse-discovery` involves low-level network system permissions and bindings to a Rust engine, developing for it requires a specific local environment configuration.

## Environment Setup

1. **Workspace Root:** Ensure you are developing from the root `netpulse` workspace.
2. **Install Dependencies:**
   ```bash
   uv sync
   ```

## Running Tests

To avoid the need for `sudo` and raw socket capabilities during standard development testing, always use the `NETPULSE_MOCK` environment variable. This instructs the Rust engine and Python services to mock network traffic.

```bash
# Run unit and integration tests specific to the discovery module
NETPULSE_MOCK=1 uv run pytest packages/netpulse-discovery/tests/
```

## Modifying the Rust Engine

If you need to make modifications to the low-level Rust ARP/ICMP packet generation:
1. Navigate to the `rust/` directory at the workspace root.
2. Make your modifications to the `.rs` files.
3. Because `netpulse-discovery` relies on `netpulse-rust` via `uv` workspace resolution, the Rust binary will automatically be recompiled using PyO3 and Maturin the next time you run `uv sync` or invoke the python environment.

## Code Standards
- All Python code must be typed using standard `typing` modules or Pydantic.
- Run `uv run ruff check` before submitting a pull request.
