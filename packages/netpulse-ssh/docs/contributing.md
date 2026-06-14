# Contributing to NetPulse SSH

Thank you for your interest in contributing to the `netpulse-ssh` package! This document outlines the process for contributing to this specific package.

## Development Environment Setup

This project uses `uv` for lightning-fast package management and `hatchling` as the build backend.

```bash
# Clone the repository
git clone https://github.com/your-org/netpulse.git
cd netpulse

# Sync the workspace and install all dependencies
uv sync

# Run the SSH specific tests
uv run pytest packages/netpulse-ssh/tests/
```

## Project Structure
- `src/netpulse/ssh/`: The actual library source code.
- `tests/unit/`: Unit tests isolating the client and runner logic.
- `tests/integration/`: Integration tests validating the API and CLI wrappers.

## Pull Request Guidelines
1. Fork the repository and create your feature branch from `main`.
2. Ensure you have added appropriate unit and integration tests for your changes.
3. Verify all tests pass cleanly using `uv run pytest`.
4. Follow standard PEP-8 style guidelines.
5. Create a descriptive PR outlining the problem solved and the approach.
