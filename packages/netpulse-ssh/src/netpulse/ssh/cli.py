import typer
import asyncio
from typing import List, Optional
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from netpulse.ssh.models import SshHostConfig, SshStatus
from netpulse.ssh.runner import SshRunnerService

app = typer.Typer(help="NetPulse SSH: High-speed concurrent command runner.", no_args_is_help=True)
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
):
    """
    Open an interactive SSH shell session with a single target host.
    """
    config = SshHostConfig(
        ip=host,
        port=port,
        username=username,
        password=password if password else None,
    )

    async def run_shell():
        runner = SshRunnerService()
        with console.status(f"[bold cyan]Connecting to {host}...", spinner="dots"):
            # The actual shell will take over standard IO, so we exit the status context quickly
            pass
        await runner.interactive_shell(config, term_type=term_type)

    asyncio.run(run_shell())

if __name__ == "__main__":
    app()
