# Architecture

The `netpulse-ssh` package is architected to perform massively concurrent, non-blocking SSH executions across networking infrastructure.

## Component Flow

1. **API / CLI Layer (`netpulse.ssh.api` / `netpulse.ssh.cli`)**
   - Ingests a list of `SshHostConfig` requests containing targets, credentials, and connection timeouts.
   - Dispatches them to the runner.

2. **Runner Service (`netpulse.ssh.runner.SshRunnerService`)**
   - Uses `asyncio.gather` to launch parallel, non-blocking asynchronous routines for every target device.
   - Collates outputs, latencies, and negotiation details into a structured `SshExecutionAudit` domain model.

3. **Smart SSH Client (`netpulse.ssh.runner.SmartSshClient`)**
   - Leverages `asyncssh` to connect to devices.
   - Automatically detects strict OpenSSH cipher drops and falls back dynamically to legacy algorithms (e.g., `diffie-hellman-group1-sha1`, `3des-cbc`) which are frequently required for older Cisco or Juniper gear.
   - Automatically injects configuration prerequisites, specifically sending `terminal length 0` to disable pagination before executing the desired command.
