# Automated Deployment Engine (Playbooks)

`netpulse-ssh` includes a powerful **Automated Deployment Engine** that shifts the tool from a simple command runner to a fully-fledged "Infrastructure as Code" (IaC) deployment engine. Systems engineers can easily define complex, multi-step server configurations in YAML and deploy them concurrently across hundreds of hosts.

## Core Concepts

The engine is built around two primary YAML definitions:
1. **Inventory (`hosts.yaml`)**: Defines the target hosts, grouping them logically and storing their respective SSH credentials.
2. **Playbook (`deploy.yaml`)**: Defines a sequential list of tasks (commands) to execute on the targets.

By decoupling the *what* (Playbook) from the *where* (Inventory), you can reuse your deployment scripts across different environments (e.g., staging vs. production).

---

## 1. Inventory Configuration

The inventory file allows you to define groups of hosts. Each host can have its own customized authentication parameters.

**`hosts.yaml` Example:**
```yaml
groups:
  web_servers:
    hosts:
      - ip: "192.168.1.10"
        username: "admin"
        password: "secretpassword"
        port: 22
      - ip: "192.168.1.11"
        username: "root"
        ssh_key: "/home/user/.ssh/id_rsa"
  
  cisco_routers:
    hosts:
      - ip: "10.0.0.1"
        username: "admin"
        password: "ciscopassword"
        enable_password: "ciscoenable"
```

### Supported Host Parameters:
- `ip` *(required)*: The target IP address or hostname.
- `username` *(optional)*: SSH login username. Default is `root` if omitted in the CLI.
- `password` *(optional)*: SSH login password.
- `ssh_key` *(optional)*: Absolute or relative path to a private SSH key file.
- `enable_password` *(optional)*: Cisco privilege EXEC mode password.
- `port` *(optional)*: SSH port, defaults to 22.

---

## 2. Playbook Configuration

A Playbook defines an array of commands that will execute sequentially on the targeted inventory. The deployment engine ensures the same underlying SSH connection is reused for the entire sequence, making it highly efficient.

**`deploy.yaml` Example:**
```yaml
name: "Setup Ubuntu Web Servers"
tasks:
  - name: "Update APT repositories"
    command: "apt-get update"
    timeout: 120

  - name: "Upgrade system packages"
    command: "apt-get upgrade"
    expect:
      - prompt: "Do you want to continue.*\\[Y/n\\]"
        send: "Y\n"

  - name: "Install Nginx"
    command: "apt-get install nginx -y"
```

### Task Parameters:
- `name` *(required)*: A human-readable description of the task.
- `command` *(required)*: The actual bash or CLI command to execute on the remote device.
- `timeout` *(optional)*: Override the global timeout for this specific task (in seconds). Useful for long-running operations like `apt-get update`.
- `expect` *(optional)*: Defines rules for the Interactive "Expect" Engine.

---

## 3. Interactive "Expect" Engine

Certain CLI commands (like system upgrades or custom installer scripts) pause and prompt the user for interactive input. Normally, this breaks automation pipelines. 

`netpulse-ssh` solves this with an integrated **Expect Engine**. You can program the deployment engine to actively scan the standard output byte stream for specific regex patterns and automatically reply.

```yaml
    expect:
      - prompt: "Proceed with reload\\? \\[confirm\\]"
        send: "\n"
      - prompt: "Enter new UNIX password:"
        send: "SecurePass123!\n"
```
*Note: Because the `prompt` is evaluated as a Python Regular Expression, ensure you escape special regex characters (like `?`, `[`, `]`) using double backslashes (`\\`). Include `\n` in your `send` string to emulate pressing the Enter key.*

---

## 4. Running a Deployment

Once your YAML files are defined, orchestrating the deployment is as simple as running the `deploy` subcommand:

```bash
netpulse-ssh deploy --inventory hosts.yaml --script deploy.yaml
```

**What happens under the hood?**
1. The CLI parses both YAML files, validating the schemas.
2. It generates connection configurations for every host listed in the inventory.
3. The `SshRunnerService` initiates concurrent SSH sessions to all hosts simultaneously.
4. For each host, the tasks defined in the Playbook are executed sequentially. If `expect` rules exist, the engine streams the output buffer, replying instantaneously upon regex matches.
5. Finally, a rich table summary is printed to the console detailing latency, success status, and error logs.
