# Contributing Guidelines

Thank you for your interest in contributing to `netpulse-subnet`!

## Local Development Setup

We manage dependencies using `uv` and build the package using `hatchling`.

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/netpulse.git
   cd netpulse
   ```

2. **Sync the workspace**:
   Since `netpulse-subnet` is part of a larger workspace, simply run `uv sync` from the workspace root. This creates a virtual environment and installs `netpulse-subnet` in editable mode.
   ```bash
   uv sync
   ```

3. **Running the package locally**:
   ```bash
   uv run netpulse-subnet --help
   ```

## Pull Request Process

1. Create a descriptive branch (`git checkout -b feature/vlsm-optimizations`).
2. Implement your feature or bugfix.
3. Ensure all tests pass (see `testing.md`).
4. Ensure code formatting is clean (we recommend using standard `ruff` or `black` formatting).
5. Submit a PR against the `main` branch.

## Namespace Considerations

`netpulse-subnet` is packaged as an implicit namespace package (`src/netpulse/subnet`). When adding new directories under `src/netpulse/`, **DO NOT** create `__init__.py` files in the `src/netpulse` root directory itself. Only create `__init__.py` files inside your inner packages (e.g., `src/netpulse/subnet/__init__.py`).
