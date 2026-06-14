# Design Decisions

## Decoupling

Previously, the SSH execution engine within `netpulse-core` tightly coupled the execution runtime with a native SQLite `DatabaseService`. 

In `netpulse-ssh`, this logic was purposefully inverted:
1. **Runner Agnosticism**: The `SshRunnerService` does absolutely zero persistence. It only yields a fully populated `SshExecutionAudit` model in memory.
2. **Caller Responsibility**: The invoker (e.g., the monolithic `netpulse-api`) is now responsible for catching the domain model and applying it to its local `DatabaseService`.

This architectural pivot guarantees that `netpulse-ssh` can be pulled off the shelf and utilized natively inside other Python applications completely independent of the broader `netpulse` ecosystem.

## Error Handling
Exceptions experienced on individual devices (e.g. `ConnectionRefusedError`, timeouts, authentication failures) are isolated at the `SmartSshClient` scope. They mutate the individual `SshHostResult.status` to `FAILED` and populate `error_message`, ensuring that a single unresponsive device does not crash the broader concurrent runtime array.
