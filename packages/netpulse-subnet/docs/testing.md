# Testing

`netpulse-subnet` relies on `pytest` for robust unit and integration testing.

## Running Tests

From the `packages/netpulse-subnet/` directory, you can run the test suite isolated from the rest of the workspace:

```bash
cd packages/netpulse-subnet
uv run pytest
```

Alternatively, you can run tests from the workspace root, which will test the entire `netpulse` ecosystem simultaneously:
```bash
uv run pytest
```

## Test Structure

- **`tests/unit/test_subnet.py`**: Validates the pure business logic algorithms (VLSM calculations, FLSM mathematical splitting, IP lookups).
- **`tests/integration/test_api_subnet.py`**: Spawns a `TestClient` for the FastAPI app to ensure REST endpoints format and return data correctly.
- **`tests/integration/test_cli_subnet.py`**: Uses Typer's `CliRunner` to ensure the Terminal UI commands parse inputs correctly and do not crash on invalid subnet arguments.

## Adding New Tests
If you submit a Pull Request adding new functionality, please ensure you write corresponding tests inside the `tests/unit/` folder. All code should be covered by at least one happy path and one error path (e.g., invalid IP address handling).
