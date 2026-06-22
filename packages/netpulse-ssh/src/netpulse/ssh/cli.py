import typer
import asyncio
from typing import List, Optional
from rich.console import Console
from rich.table import Table
from rich import print as rprint
import yaml

from netpulse.ssh.models import SshHostConfig, SshStatus, Playbook, Inventory
from netpulse.ssh.runner import SshRunnerService

app = typer.Typer(help="NetPulse SSH: High-speed concurrent command runner.", no_args_is_help=True)
scp_app = typer.Typer(help="SCP file transfer commands.", no_args_is_help=True)
app.add_typer(scp_app, name="scp")

console = Console()

@app.callback()
def callback():
    """NetPulse SSH CLI."""
    pass

@app.command("execute")
def execute(
    hosts: List[str] = typer.Argument(..., help="List of IP addresses to target."),
    command: str = typer.Option(..., "--command", "-c", help="Command to execute."),
    username: str = typer.Option(..., "--user", "-u", help="SSH Username.", prompt=True),
    password: str = typer.Option("", "--pass", "-p", help="SSH Password.", hide_input=True, prompt="Password (leave empty if using keys)"),
    enable_password: str = typer.Option("", "--enable", "-e", help="Cisco enable password.", hide_input=True),
    port: int = typer.Option(22, "--port", help="SSH port."),
    jump_host: str = typer.Option(None, "--jump-host", "-J", help="ProxyJump Bastion host (e.g., admin@bastion.local)."),
    bastion_pass: str = typer.Option(None, "--bastion-pass", help="Password for the Bastion host.", hide_input=True),
):
    """
    Execute a command concurrently across multiple SSH hosts and aggregate the results.
    """
    hosts_config = [
        SshHostConfig(
            ip=ip,
            port=port,
            username=username,
            password=password if password else None,
            enable_password=enable_password if enable_password else None,
            jump_host=jump_host,
            bastion_pass=bastion_pass,
        ) for ip in hosts
    ]

    async def run():
        runner = SshRunnerService()
        with console.status(f"[bold cyan]Executing '{command}' across {len(hosts)} hosts...", spinner="dots"):
            audit = await runner.execute_concurrently(hosts_config, command)
        
        table = Table(title=f"SSH Execution Summary: '{command}'")
        table.add_column("Host IP", justify="left", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Latency (ms)", justify="right", style="magenta")
        table.add_column("Output / Error", justify="left", style="green")

        for res in audit.results:
            if res.status == SshStatus.SUCCESS:
                status_str = "[bold green]SUCCESS[/bold green]"
                output = res.stdout.strip()[:100] + ("..." if len(res.stdout) > 100 else "") if res.stdout else "No output"
            else:
                status_str = "[bold red]FAILED[/bold red]"
                output = f"[red]{res.error_message}[/red]"

            table.add_row(res.ip, status_str, f"{res.latency_ms}ms", output)

        console.print(table)
        rprint(f"[bold]Total Success:[/bold] {audit.success_count} | [bold]Total Failed:[/bold] {audit.failed_count}")

    asyncio.run(run())

@app.command("shell")
def shell(
    host: str = typer.Argument(..., help="Target host IP address."),
    username: str = typer.Option(..., "--user", "-u", help="SSH Username.", prompt=True),
    password: str = typer.Option("", "--pass", "-p", help="SSH Password.", hide_input=True, prompt="Password (leave empty if using keys)"),
    port: int = typer.Option(22, "--port", help="SSH port."),
    term_type: str = typer.Option("xterm-256color", "--term", help="Terminal type for interactive shell."),
    jump_host: str = typer.Option(None, "--jump-host", "-J", help="ProxyJump Bastion host (e.g., admin@bastion.local)."),
    bastion_pass: str = typer.Option(None, "--bastion-pass", help="Password for the Bastion host.", hide_input=True),
):
    """
    Open an interactive SSH shell session with a single target host.
    """
    config = SshHostConfig(
        ip=host,
        port=port,
        username=username,
        password=password if password else None,
        jump_host=jump_host,
        bastion_pass=bastion_pass,
    )

    async def run_shell():
        runner = SshRunnerService()
        with console.status(f"[bold cyan]Connecting to {host}...", spinner="dots"):
            # The actual shell will take over standard IO, so we exit the status context quickly
            pass
        await runner.interactive_shell(config, term_type=term_type)

    asyncio.run(run_shell())

@app.command("deploy")
def deploy(
    inventory_file: str = typer.Option(..., "--inventory", "-i", help="YAML inventory file."),
    script_file: str = typer.Option(..., "--script", "-s", help="YAML playbook script file.")
):
    """
    Automated Deployment Engine: Execute a playbook sequence across an inventory.
    """
    # 1. Parse playbook
    try:
        with open(script_file, 'r') as f:
            playbook_data = yaml.safe_load(f)
        playbook = Playbook(**playbook_data)
    except Exception as e:
        rprint(f"[bold red]Failed to parse playbook script '{script_file}':[/bold red] {e}")
        raise typer.Exit(1)

    # 2. Parse inventory
    try:
        with open(inventory_file, 'r') as f:
            inventory_data = yaml.safe_load(f)
        inventory = Inventory(**inventory_data)
    except Exception as e:
        rprint(f"[bold red]Failed to parse inventory file '{inventory_file}':[/bold red] {e}")
        raise typer.Exit(1)

    # 3. Build SshHostConfig list
    hosts_config = []
    for group_name, group in inventory.groups.items():
        for host in group.hosts:
            hosts_config.append(
                SshHostConfig(
                    ip=host.ip,
                    port=host.port if host.port is not None else 22,
                    username=host.username if host.username is not None else "root", # Defaulting to root if not provided or handle missing
                    password=host.password,
                    enable_password=host.enable_password,
                    ssh_key=host.ssh_key,
                )
            )

    async def run():
        runner = SshRunnerService()
        with console.status(f"[bold cyan]Deploying playbook '{playbook.name}' across {len(hosts_config)} hosts...", spinner="dots"):
            audit = await runner.execute_playbook_concurrently(hosts_config, playbook)
        
        table = Table(title=f"Deployment Summary: '{playbook.name}'")
        table.add_column("Host IP", justify="left", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Latency (ms)", justify="right", style="magenta")
        table.add_column("Output / Error", justify="left", style="green")

        for res in audit.results:
            if res.status == SshStatus.SUCCESS:
                status_str = "[bold green]SUCCESS[/bold green]"
                output = res.stdout.strip()[:150] + ("..." if len(res.stdout) > 150 else "") if res.stdout else "No output"
            else:
                status_str = "[bold red]FAILED[/bold red]"
                output = f"[red]{res.error_message}[/red]"

            table.add_row(res.ip, status_str, f"{res.latency_ms}ms", output)

        console.print(table)
        rprint(f"[bold]Total Success:[/bold] {audit.success_count} | [bold]Total Failed:[/bold] {audit.failed_count}")

    asyncio.run(run())

@scp_app.command("push")
def scp_push(
    hosts: List[str] = typer.Argument(..., help="List of IP addresses to target."),
    src: str = typer.Option(..., "--src", help="Local source file path."),
    dest: str = typer.Option(..., "--dest", help="Remote destination directory or file path."),
    username: str = typer.Option(..., "--user", "-u", help="SSH Username.", prompt=True),
    password: str = typer.Option("", "--pass", "-p", help="SSH Password.", hide_input=True, prompt="Password (leave empty if using keys)"),
    port: int = typer.Option(22, "--port", help="SSH port."),
    jump_host: str = typer.Option(None, "--jump-host", "-J", help="ProxyJump Bastion host (e.g., admin@bastion.local)."),
    bastion_pass: str = typer.Option(None, "--bastion-pass", help="Password for the Bastion host.", hide_input=True),
):
    """
    Push a local file to multiple remote hosts concurrently using SCP.
    """
    hosts_config = [
        SshHostConfig(
            ip=ip,
            port=port,
            username=username,
            password=password if password else None,
            jump_host=jump_host,
            bastion_pass=bastion_pass,
        ) for ip in hosts
    ]

    async def run():
        runner = SshRunnerService()
        with console.status(f"[bold cyan]Pushing '{src}' to {len(hosts)} hosts...", spinner="dots"):
            audit = await runner.execute_scp_push_concurrently(hosts_config, src, dest)
        
        table = Table(title=f"SCP Push Summary: '{src}' -> '{dest}'")
        table.add_column("Host IP", justify="left", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Latency (ms)", justify="right", style="magenta")
        table.add_column("Output / Error", justify="left", style="green")

        for res in audit.results:
            if res.status == SshStatus.SUCCESS:
                status_str = "[bold green]SUCCESS[/bold green]"
                output = res.stdout.strip()[:100] + ("..." if len(res.stdout) > 100 else "") if res.stdout else "No output"
            else:
                status_str = "[bold red]FAILED[/bold red]"
                output = f"[red]{res.error_message}[/red]"

            table.add_row(res.ip, status_str, f"{res.latency_ms}ms", output)

        console.print(table)
        rprint(f"[bold]Total Success:[/bold] {audit.success_count} | [bold]Total Failed:[/bold] {audit.failed_count}")

    asyncio.run(run())

@scp_app.command("pull")
def scp_pull(
    hosts: List[str] = typer.Argument(..., help="List of IP addresses to target."),
    src: str = typer.Option(..., "--src", help="Remote source file path."),
    dest: str = typer.Option(..., "--dest", help="Local destination directory."),
    username: str = typer.Option(..., "--user", "-u", help="SSH Username.", prompt=True),
    password: str = typer.Option("", "--pass", "-p", help="SSH Password.", hide_input=True, prompt="Password (leave empty if using keys)"),
    port: int = typer.Option(22, "--port", help="SSH port."),
    jump_host: str = typer.Option(None, "--jump-host", "-J", help="ProxyJump Bastion host (e.g., admin@bastion.local)."),
    bastion_pass: str = typer.Option(None, "--bastion-pass", help="Password for the Bastion host.", hide_input=True),
):
    """
    Pull a remote file from multiple hosts concurrently, saving into IP-segregated folders.
    """
    hosts_config = [
        SshHostConfig(
            ip=ip,
            port=port,
            username=username,
            password=password if password else None,
            jump_host=jump_host,
            bastion_pass=bastion_pass,
        ) for ip in hosts
    ]

    async def run():
        runner = SshRunnerService()
        with console.status(f"[bold cyan]Pulling '{src}' from {len(hosts)} hosts...", spinner="dots"):
            audit = await runner.execute_scp_pull_concurrently(hosts_config, src, dest)
        
        table = Table(title=f"SCP Pull Summary: '{src}' -> '{dest}'")
        table.add_column("Host IP", justify="left", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Latency (ms)", justify="right", style="magenta")
        table.add_column("Output / Error", justify="left", style="green")

        for res in audit.results:
            if res.status == SshStatus.SUCCESS:
                status_str = "[bold green]SUCCESS[/bold green]"
                output = res.stdout.strip()[:100] + ("..." if len(res.stdout) > 100 else "") if res.stdout else "No output"
            else:
                status_str = "[bold red]FAILED[/bold red]"
                output = f"[red]{res.error_message}[/red]"

            table.add_row(res.ip, status_str, f"{res.latency_ms}ms", output)

        console.print(table)
        rprint(f"[bold]Total Success:[/bold] {audit.success_count} | [bold]Total Failed:[/bold] {audit.failed_count}")

    asyncio.run(run())

if __name__ == "__main__":
    app()
