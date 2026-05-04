# NetPulse — AI Context Document

## 1. Project Overview

NetPulse is a network operations platform designed to provide a unified, high-performance, and developer-friendly toolbox for network engineers, cybersecurity analysts, DevOps engineers, and enterprise teams.

It is not a simple CLI tool. It is a scalable system that evolves into:

* A professional network engineering toolbox
* A monitoring and analytics platform
* An automation engine for infrastructure
* A foundation for a future SaaS product

The system is designed with a strong emphasis on:

* Performance (Rust-powered core)
* Modularity (clear separation of concerns)
* Extensibility (plugin ecosystem)
* Usability (modern CLI + GUI)
* Automation readiness (API-first design)

---

## 2. Core Objectives

### Technical Objectives

* Build a high-performance network discovery and analysis engine
* Integrate Rust for performance-critical operations
* Provide a clean and scalable Python architecture
* Ensure compatibility with enterprise environments
* Enable automation via API and CLI

### Learning Objectives

* Master Rust for systems and networking
* Strengthen network engineering knowledge
* Build production-grade software architecture
* Develop a real-world, scalable product

### Product Objectives

* Create an open-source community tool
* Build a foundation for enterprise usage
* Enable future SaaS evolution

---

## 3. Target Users

Primary users:

* Network engineers
* Cybersecurity analysts
* DevOps engineers
* Internal enterprise IT teams

Secondary users:

* Students learning networking
* System administrators
* Infrastructure engineers

---

## 4. System Architecture

NetPulse follows a layered architecture with strict separation of concerns.

### Architecture Flow

CLI → Core → Engine → Rust
GUI → API → Core → Engine → Rust

### Layers

#### 1. Interface Layer

* CLI (Typer)
* GUI (React / Next.js)

Responsibilities:

* User interaction
* Input parsing
* Output formatting

Restrictions:

* Must not contain business logic
* Must not call Rust directly

---

#### 2. API Layer (FastAPI)

Responsibilities:

* Expose system capabilities via HTTP
* Serve GUI and future SaaS
* Validate inputs

Restrictions:

* Must not contain business logic
* Must call Core layer only

---

#### 3. Core Layer (Business Logic)

Responsibilities:

* Define application workflows
* Orchestrate operations
* Structure data models
* Apply business rules

Examples:

* DiscoveryService
* SSHService

Restrictions:

* No CLI code
* No API code
* No direct Rust calls

---

#### 4. Engine Layer

Responsibilities:

* Execute tasks
* Handle concurrency (async)
* Interface with Rust

Sub-components:

* Python execution modules
* Rust bindings

---

#### 5. Rust Core

Responsibilities:

* High-performance networking
* Packet crafting (ARP, ICMP, TCP)
* Concurrent scanning

Integration:

* Exposed via pyo3 bindings
* Imported as Python module

---

#### 6. Infrastructure Layer

Responsibilities:

* Database (SQLite → PostgreSQL)
* Logging (structured JSON)
* Configuration (YAML/TOML)
* Security (credentials, vaults)

---

## 5. Technology Stack

### Backend

* Python 3
* Typer (CLI)
* FastAPI (API)

### Frontend

* React / Next.js
* Tailwind CSS

### Systems Layer

* Rust
* pyo3
* maturin

### Database

* SQLite (local)
* PostgreSQL (enterprise)

### DevOps

* GitHub Actions
* Docker (future)

---

## 6. Development Philosophy

### 1. Modular Design

Each component must be independent and replaceable.

### 2. Separation of Concerns

No mixing of:

* CLI and business logic
* API and engine logic
* Rust and interface layers

### 3. Incremental Development

* Build one feature at a time
* Validate before expanding
* Avoid premature optimization

### 4. Performance Where It Matters

* Use Rust only for critical paths
* Keep orchestration in Python

### 5. API-First Mindset

All features must be usable via API.

### 6. Offline-First Design

System must work without internet access.

---

## 7. Current Milestone

### Milestone 1 — Network Discovery (ARP + ICMP)

Scope:

* Discover devices in a network
* Use ARP for local networks
* Use ICMP for reachability

Deliverables:

* Rust-based scanning engine
* Python orchestration layer
* CLI command
* API endpoint
* Structured JSON output

---

## 8. Data Model Philosophy

Data must be structured, extensible, and consistent.

Example:

{
"ip": "192.168.1.1",
"hostname": "router",
"mac": "00:11:22:33:44:55",
"vendor": "Cisco",
"status": "up",
"latency": 10
}

Rules:

* Always return structured data
* Avoid raw strings
* Keep models extensible

---

## 9. Concurrency Model

* Python: asyncio for orchestration
* Rust: native concurrency for performance

Goals:

* High-speed scanning
* Efficient resource usage
* Scalable execution

---

## 10. Error Handling Philosophy

NetPulse follows a resilient error model.

Rules:

* Do not stop entire operations on partial failure
* Return partial results
* Log all errors
* Provide meaningful error messages

---

## 11. Logging & Observability

* Structured JSON logs
* Debug mode support
* Execution tracing
* Performance metrics

Logs must:

* Be machine-readable
* Include context
* Avoid sensitive data

---

## 12. Plugin System Vision

NetPulse supports external plugins.

Capabilities:

* Vendor-specific integrations
* Custom automation modules
* Extended analytics

Supported languages:

* Python
* Rust

---

## 13. Security Considerations

* Secure credential handling
* Support for environment variables
* Future credential vault integration
* Avoid storing plaintext secrets

---

## 14. Testing Strategy

* Unit tests (Python + Rust)
* Integration tests
* Virtual lab testing (GNS3, containers)
* CI pipeline validation

---

## 15. AI Collaboration Principles

When using AI:

* Always follow architecture rules
* Never generate code that violates layering
* Prefer step-by-step implementation
* Validate before integrating

AI must:

* Respect this document
* Follow AI_RULES.md
* Generate modular, clean code

---

## 16. Long-Term Vision

NetPulse evolves into:

* Enterprise network management platform
* Monitoring and alerting system
* Automation engine
* SaaS product

Key features later:

* Real-time monitoring
* Anomaly detection
* Multi-user collaboration
* Role-based access

---

## 17. Non-Goals (Important Boundaries)

NetPulse is NOT:

* A quick script
* A monolithic tool
* A UI-only project

Avoid:

* Tight coupling
* Hardcoded logic
* Skipping architecture layers

---

## 18. Development Mindset

* Think in systems, not scripts
* Build for scalability from the start
* Keep code clean and maintainable
* Prioritize clarity over complexity
* Use Abstraction when possible

