# NetPulse — AI Workflows & Prompt System

## 1. Purpose

This document defines **how to work with AI consistently** to build NetPulse.
It standardizes:

* Task execution patterns
* Prompt templates
* Review & validation loops
* Iteration strategy

Goal: turn AI into a **reliable engineering assistant**, not a code generator.

---

## 2. Core Principles

### 2.1 Design First, Code Second

* ALWAYS request design/plan before code for non-trivial features
* Validate against AI_CONTEXT.md and AI_RULES.md

### 2.2 Small, Verifiable Steps

* Break work into small tasks (≤ 1 file or 1 responsibility)
* Prefer incremental commits

### 2.3 Single Concern per Prompt

* Each prompt targets one layer or one component
* Avoid “build everything” prompts

### 2.4 Deterministic Outputs

* Ask for explicit inputs/outputs
* Request types and schemas

### 2.5 Continuous Validation

* After each step: review, test, refine

---

## 3. Standard Workflow Lifecycle

### Phase 1 — Define Task

* State objective
* Scope boundaries (in/out)
* Target layer (CLI/Core/Engine/API/Rust)

### Phase 2 — Design

* Request architecture for the task
* Define interfaces, data models
* Identify dependencies

### Phase 3 — Implementation (Step-by-step)

* Generate code in small units
* Keep each unit testable

### Phase 4 — Validation

* Add tests
* Check against rules
* Review edge cases

### Phase 5 — Integration

* Connect with adjacent layers
* Verify end-to-end behavior

---

## 4. Prompt Templates

### 4.1 Feature Design Prompt

Task: <feature name>

Context:

* Follow AI_CONTEXT.md
* Respect AI_RULES.md

Scope:

* Target layer: <layer>
* In scope: <items>
* Out of scope: <items>

Requirements:

* Inputs: <types>
* Outputs: <types>
* Constraints: <performance/security>

Deliver:

* Architecture (modules, files)
* Data models
* Function/class interfaces
* Flow diagram (text)

---

### 4.2 Implementation Prompt (Core)

Task: Implement <service/class>

Context:

* Follow AI_CONTEXT.md
* Respect AI_RULES.md

Constraints:

* No CLI/API logic
* No direct Rust calls

Requirements:

* Clear interfaces
* Type hints
* Pure logic

Deliver:

* Code (modular)
* Short explanation

---

### 4.3 Implementation Prompt (Engine)

Task: Implement <engine module>

Context:

* Follow AI_CONTEXT.md
* Respect AI_RULES.md

Constraints:

* Async where needed
* Can call Rust bindings
* No business logic

Deliver:

* Code
* Concurrency approach
* Error handling

---

### 4.4 Implementation Prompt (CLI)

Task: Implement CLI command <name>

Context:

* Follow AI_CONTEXT.md
* Respect AI_RULES.md

Constraints:

* Call Core only
* Handle input/output only

Deliver:

* Typer command
* Options/flags
* Output formatting strategy

---

### 4.5 Implementation Prompt (API)

Task: Implement API endpoint <route>

Context:

* Follow AI_CONTEXT.md
* Respect AI_RULES.md

Constraints:

* Call Core only
* Validate inputs
* Return JSON

Deliver:

* FastAPI route
* Request/response models

---

### 4.6 Rust Module Prompt

Task: Implement Rust module <name>

Context:

* Follow AI_CONTEXT.md
* Respect AI_RULES.md

Requirements:

* Performance-focused
* Safe concurrency

Deliver:

* Rust code
* pyo3 binding interface
* Python usage example

---

### 4.7 Testing Prompt

Task: Write tests for <component>

Context:

* Follow AI_CONTEXT.md
* Respect AI_RULES.md

Requirements:

* Cover success cases
* Cover failure cases
* Edge cases

Deliver:

* Unit tests
* Integration notes

---

### 4.8 Debugging Prompt

Problem:
<error/log>

Context: <what was running>

Expected: <expected behavior>

Ask:

* Root cause
* Fix proposal
* Preventive measures

---

## 5. Task Decomposition Strategy

When facing a feature, split into:

1. Data model
2. Core service
3. Engine execution
4. CLI command
5. API endpoint
6. Tests

Never skip steps.

---

## 6. Iteration Rules

* Do not move to next step until current is validated
* Refactor early, not late
* Keep PRs small

---

## 7. Review Checklist (Use After Each Step)

* Does it respect architecture layers?
* Is logic in the correct layer?
* Are types defined?
* Is code modular?
* Are errors handled?
* Are tests possible?

---

## 8. Anti-Patterns in AI Usage

Avoid prompts like:

* “Build the whole feature”
* “Generate full project”

Avoid outputs that:

* Mix layers
* Skip validation
* Overcomplicate design

---

## 9. Efficiency Tips

* Reuse templates
* Keep prompts consistent
* Reference context files always

---

## 10. Evolution Strategy

As project grows:

* Add new templates
* Refine workflows
* Introduce advanced patterns (plugins, monitoring)
