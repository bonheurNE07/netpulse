# NetPulse — AI Rules & Guardrails

## 1. Purpose of This Document

This document defines the strict rules that any AI assistant MUST follow when generating, modifying, or suggesting code for NetPulse.

These rules exist to:

* Protect the architecture
* Ensure code quality and consistency
* Prevent technical debt
* Maintain scalability and extensibility

Any AI output that violates these rules is considered INVALID.

---

## 2. Absolute Architecture Rules (NON-NEGOTIABLE)

### 2.1 Layer Isolation

The system is composed of strict layers:

* CLI (apps/cli)
* API (apps/api)
* Core (packages/core)
* Engine (packages/engine)
* Rust (rust/)

Rules:

* CLI MUST NEVER contain business logic

* CLI MUST NEVER call Rust directly

* CLI MUST ONLY call Core layer

* API MUST NEVER contain business logic

* API MUST ONLY call Core layer

* Core MUST NOT depend on CLI or API

* Core MUST NOT call Rust directly

* Core MUST ONLY call Engine layer

* Engine is the ONLY layer allowed to call Rust

* Rust MUST NOT know about Python structure

---

### 2.2 Data Flow Integrity

Allowed flow:

CLI → Core → Engine → Rust
GUI → API → Core → Engine → Rust

Forbidden:

* CLI → Engine
* CLI → Rust
* API → Engine (must go through Core)
* Core → CLI/API

---

## 3. Code Organization Rules

### 3.1 File Placement

* CLI commands → apps/cli
* API routes → apps/api
* Business logic → packages/core
* Execution logic → packages/engine
* Infrastructure → packages/infra

AI MUST NEVER place code in the wrong layer.

---

### 3.2 Naming Conventions

* Classes: PascalCase
* Functions: snake_case
* Variables: snake_case
* Constants: UPPER_CASE

Examples:

* DiscoveryService
* run_discovery

---

### 3.3 File Structure

Each module should be:

* Small
* Focused
* Single responsibility

AI MUST split large files into smaller modules.

---

## 4. Business Logic Rules

### 4.1 Core Layer Rules

Core is the brain of the system.

AI MUST:

* Implement services (e.g., DiscoveryService)
* Keep logic pure and testable
* Use clear interfaces

AI MUST NOT:

* Print output
* Use CLI formatting
* Handle HTTP logic

---

### 4.2 Engine Layer Rules

Engine is responsible for execution.

AI MUST:

* Handle async operations
* Coordinate tasks
* Call Rust bindings

AI MUST NOT:

* Contain business decisions
* Contain UI logic

---

### 4.3 Rust Integration Rules

* Rust functions must be wrapped via pyo3
* Rust must be called ONLY from Engine
* Python must not reimplement Rust logic

---

## 5. Coding Standards

### 5.1 Type Safety

* Use type hints everywhere
* Prefer explicit types over implicit

Example:

```python
from typing import List

def discover(network: str) -> List[Device]:
    ...
```

---

### 5.2 Async Usage

* Use asyncio for I/O operations
* Avoid blocking calls

---

### 5.3 Error Handling

* Use structured exceptions
* Never silently fail
* Return partial results when possible

---

### 5.4 Logging

* Use structured logging
* No print() in production code

---

## 6. Data Handling Rules

### 6.1 Structured Output

* Always return structured data (dict or models)
* No raw strings

### 6.2 Models

* Use consistent schemas
* Ensure extensibility

---

## 7. Configuration Rules

* No hardcoded values
* Use config system (YAML/TOML/env)

---

## 8. Security Rules

* Never expose credentials
* Never log sensitive data
* Support env variables for secrets

---

## 9. Testing Rules

AI MUST:

* Write unit tests for logic
* Ensure testable design

---

## 10. Performance Rules

* Use Rust for heavy operations
* Avoid premature optimization in Python

---

## 11. CLI Rules

* CLI must only handle input/output
* Use Typer conventions
* Support flags and options

---

## 12. API Rules

* Use FastAPI best practices
* Validate inputs
* Return JSON

---

## 13. Plugin System Rules

* Plugins must not break core
* Use clear interfaces

---

## 14. Anti-Patterns (STRICTLY FORBIDDEN)

* Mixing layers
* Hardcoding values
* Duplicating logic
* Writing monolithic functions
* Ignoring type hints

---

## 15. AI Behavior Rules

When generating code, AI MUST:

1. Respect architecture
2. Generate modular code
3. Explain decisions
4. Avoid assumptions
5. Ask for clarification if needed

AI MUST NOT:

* Shortcut architecture
* Over-engineer unnecessarily
* Ignore this document
