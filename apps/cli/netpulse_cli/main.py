import sys
import os
import asyncio
import ipaddress
from typing import List, Optional

# Dynamically add the packages folder paths so we can import them from anywhere
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.insert(0, os.path.join(base_dir, "packages/core"))
sys.path.insert(0, os.path.join(base_dir, "packages/engine"))

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.align import Align
from rich import box

from netpulse_core.services.discovery import DiscoveryService
from netpulse_core.models.discovery import DiscoveryMethod
from netpulse_core.models.device import DeviceStatus

app = typer.Typer(
    name="netpulse",
    help="NetPulse: High-performance, modern network discovery and analysis CLI.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()

@app.command(name="discover", help="Scan a target CIDR network range to discover active hosts.")
def discover(
    target: str = typer.Argument(
        ...,
        help="Target CIDR network address range to scan (e.g. 172.19.57.0/24 or 192.168.1.1/32).",
    ),
    methods: Optional[List[str]] = typer.Option(
        None,
        "--method",
        "-m",
        help="Discovery protocol(s) to use: arp, icmp. Can be specified multiple times. Defaults to arp.",
    ),
    timeout: int = typer.Option(
        1000,
        "--timeout",
        "-t",
        help="Timeout in milliseconds for responses from each host.",
    ),
    interface: Optional[str] = typer.Option(
        None,
        "--interface",
        "-i",
        help="Explicit network interface to scan on (e.g. eth0, wlan0). Only used by ARP.",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format to display results: table or json.",
    ),
):
    """
    Executes a high-performance network discovery scan using raw sockets in Rust.
    Optimized for extremely rapid Layer 2 (ARP) and Layer 3 (ICMP) discovery sweeps.
    """
    # 1. Parse and validate methods
    valid_methods = {"arp": DiscoveryMethod.ARP, "icmp": DiscoveryMethod.ICMP}
    parsed_methods = []
    if not methods:
        parsed_methods = [DiscoveryMethod.ARP]
    else:
        for m in methods:
            m_lower = m.lower()
            if m_lower not in valid_methods:
                console.print(Panel(
                    f"[bold red]Error:[/] Invalid discovery method '[yellow]{m}[/]'.\n"
                    f"Supported methods are: [bold cyan]arp[/], [bold cyan]icmp[/].",
                    title="[bold red]Validation Error[/bold red]",
                    border_style="red",
                    box=box.ROUNDED,
                ))
                raise typer.Exit(code=1)
            parsed_methods.append(valid_methods[m_lower])

    # 2. Validate CIDR format before proceeding
    try:
        ipaddress.ip_network(target, strict=False)
    except ValueError as e:
        console.print(Panel(
            f"[bold red]Error:[/] Invalid target network CIDR '[yellow]{target}[/]'.\n"
            f"Details: {e}",
            title="[bold red]Malformed Target Range[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    # 3. Execute Scan with rich spinner status
    with console.status(
        f"[bold cyan]Scanning network [magenta]{target}[/] using {', '.join(m.value.upper() for m in parsed_methods)}...[/bold cyan]",
        spinner="dots"
    ):
        try:
            service = DiscoveryService()
            result = asyncio.run(service.discover_network(
                target_network=target,
                methods=parsed_methods,
                timeout_ms=timeout,
                interface=interface
            ))
        except Exception as e:
            console.print(Panel(
                f"[bold red]Scan Failed Unhandled Exception:[/] {e}",
                title="[bold red]Execution Failure[/bold red]",
                border_style="red",
                box=box.ROUNDED,
            ))
            raise typer.Exit(code=1)

    # 4. Detect Permission Denial / Raw socket error
    is_permission_error = False
    permission_err_msg = ""
    for err in result.errors:
        if "permission denied" in err.lower() or "operation not permitted" in err.lower():
            is_permission_error = True
            permission_err_msg = err
            break

    if is_permission_error:
        method_names = ", ".join(m.value for m in parsed_methods)
        warning_text = (
            f"[bold red]Error:[/] NetPulse requires elevated privileges to open raw sockets.\n\n"
            f"[bold yellow]Details:[/] {permission_err_msg}\n\n"
            f"[bold white]Why did this happen?[/]\n"
            f"  • [bold cyan]ARP Scanning (L2)[/] crafts custom ethernet frames and listens directly on raw sockets,\n"
            f"    requiring [bold cyan]CAP_NET_RAW[/] and [bold cyan]CAP_NET_ADMIN[/] capabilities or superuser privilege.\n"
            f"  • [bold cyan]ICMP Sweep (L3)[/]/ping scans utilize ICMP raw sockets which require [bold cyan]CAP_NET_RAW[/] capability.\n\n"
            f"[bold green]How to resolve this:[/]\n\n"
            f"[bold yellow]Option A: Run command via sudo (Recommended for testing)[/]\n"
            f"  [bold white]$ sudo .venv/bin/python apps/cli/netpulse_cli/main.py discover {target} --method {method_names}[/]\n\n"
            f"[bold yellow]Option B: Grant Linux Capabilities to Python interpreter (Best practice)[/]\n"
            f"  [bold white]$ sudo setcap cap_net_raw,cap_net_admin+eip $(readlink -f .venv/bin/python)[/]\n"
        )
        console.print(Panel(
            warning_text,
            title="[bold red]⚠️ Privileges Required[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    # 5. Output rendering: JSON Format
    if output_format.lower() == "json":
        json_data = result.model_dump_json(indent=2)
        console.print(Syntax(json_data, "json", theme="monokai", background_color="default"))
        if result.status == "failed":
            raise typer.Exit(code=1)
        elif result.status == "partial":
            raise typer.Exit(code=2)
        raise typer.Exit(code=0)

    # 6. Output rendering: Table Format (Default)
    # Header panel
    status_indicator = "[bold green]COMPLETED ●[/]"
    if result.status == "partial":
        status_indicator = "[bold yellow]PARTIAL ▲[/]"
    elif result.status == "failed":
        status_indicator = "[bold red]FAILED ■[/]"

    scan_summary = (
        f"[bold cyan]Target Network :[/] [white]{result.network}[/]\n"
        f"[bold cyan]Scan Methods   :[/] [white]{', '.join(str(m.value if hasattr(m, 'value') else m).upper() for m in result.methods)}[/]\n"
        f"[bold cyan]Scan Status    :[/] {status_indicator}\n"
        f"[bold cyan]Scan Duration  :[/] [yellow]{result.duration_s:.4f} seconds[/]\n"
        f"[bold cyan]Discovered     :[/] [bold green]{result.total_discovered}[/] active hosts (out of {result.stats.get('scanned', 0)} checked)"
    )

    console.print(Panel(
        Align.center(scan_summary),
        title="[bold magenta]⚡ NetPulse Scan Summary ⚡[/bold magenta]",
        border_style="magenta",
        box=box.DOUBLE,
    ))

    # Devices Table
    if result.devices:
        table = Table(
            box=box.ROUNDED,
            header_style="bold magenta",
            border_style="cyan",
            title="Discovered Active Hosts",
            title_style="bold cyan underline"
        )
        table.add_column("IP Address", style="bold cyan", justify="left")
        table.add_column("MAC Address", style="white", justify="left")
        table.add_column("RTT (Latency)", style="yellow", justify="right")
        table.add_column("Status", justify="center")
        table.add_column("Vendor", style="green", justify="left")

        # Sort hosts numerically by IP address
        try:
            sorted_devices = sorted(result.devices, key=lambda d: ipaddress.ip_address(str(d.ip)))
        except Exception:
            sorted_devices = result.devices

        for device in sorted_devices:
            mac_str = device.mac if device.mac else "[dim white]N/A[/]"
            rtt_str = f"{device.rtt_ms:.3f} ms" if device.rtt_ms is not None else "[dim white]N/A[/]"
            status_str = "[bold green]● up[/bold green]" if device.status == DeviceStatus.UP else "[bold red]● down[/bold red]"
            vendor_str = device.vendor if device.vendor else "[dim green]-[/]"

            table.add_row(
                str(device.ip),
                mac_str,
                rtt_str,
                status_str,
                vendor_str
            )

        console.print(table)
    else:
        console.print("\n[yellow]No active devices were discovered in the target subnet.[/yellow]\n")

    # Non-fatal warnings panel
    if result.errors and result.status != "failed":
        error_summary = "\n".join([f"• [bold red]Warning:[/] {err}" for err in result.errors])
        console.print(Panel(
            error_summary,
            title="[bold yellow]⚠️ Non-Fatal Scan Warnings[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED,
        ))

    # Exit code based on status
    if result.status == "failed":
        raise typer.Exit(code=1)
    elif result.status == "partial":
        raise typer.Exit(code=2)
    raise typer.Exit(code=0)

@app.command(name="version", help="Show NetPulse version information.")
def version():
    """Prints the CLI and package version details."""
    console.print("[bold magenta]NetPulse CLI[/bold magenta] version [bold cyan]0.1.0[/bold cyan]")

if __name__ == "__main__":
    app()
