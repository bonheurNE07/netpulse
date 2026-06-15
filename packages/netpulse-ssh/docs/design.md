# Design Decisions

## Decoupling

Previously, the SSH execution engine within `netpulse-core` tightly coupled the execution runtime with a native SQLite `DatabaseService`. 

In `netpulse-ssh`, this logic was purposefully inverted:
1. **Runner Agnosticism**: The `SshRunnerService` does absolutely zero persistence. It only yields a fully populated `SshExecutionAudit` model in memory.
2. **Caller Responsibility**: The invoker (e.g., the monolithic `netpulse-api`) is now responsible for catching the domain model and applying it to its local `DatabaseService`.

This architectural pivot guarantees that `netpulse-ssh` can be pulled off the shelf and utilized natively inside other Python applications completely independent of the broader `netpulse` ecosystem.

## Error Handling
Exceptions experienced on individual devices (e.g. `ConnectionRefusedError`, timeouts, authentication failures) are isolated at the `SmartSshClient` scope. They mutate the individual `SshHostResult.status` to `FAILED` and populate `error_message`, ensuring that a single unresponsive device does not crash the broader concurrent runtime array.

## Pure Python PTY Emulator vs OS Native Wrapping
When designing the `netpulse-ssh shell` interactive terminal feature, we evaluated two architectural paths:
1. **OS Native Wrapping**: Simply spawning a `subprocess.call(["ssh", ...])` and letting the OS natively handle the terminal.
2. **Pure Python PTY Bridge**: Manually catching keystrokes and mapping IO streams directly to the `asyncssh` byte tunnels.

**Decision**: We committed to the **Pure Python PTY Bridge**.
While OS wrapping is technically easier, it breaks the core requirement of automation. Native `ssh` binaries strictly prohibit passing passwords via CLI flags (`-p`) or injecting complex Cisco `enable` escalation sequences programmatically. By building our own keystroke interpreter (utilizing `msvcrt.getch()` on Windows to intercept live inputs and translate ANSI arrow keys), `netpulse-ssh` acts identically to a standalone client like PuTTY, ensuring it remains highly programmable and API-ready.

## Legacy Cryptography Auto-Negotiation
Modern native SSH clients silently upgrade their security postures, often completely dropping support for `ssh-rsa` and `diffie-hellman-group1-sha1`. This immediately breaks access to 90% of legacy Cisco and Juniper networking gear running older firmware. 

Instead of forcing users to build complex `ssh_config` files, the `SmartSshClient` intercepts `ProtocolError` and `DisconnectError` exceptions during the initial handshake. If a key-exchange failure is detected, it automatically rebuilds the payload matrix, dynamically injecting a massive array of deprecated legacy algorithms and safely reconnecting. This provides a "Zero-Config" guarantee for network engineers.
