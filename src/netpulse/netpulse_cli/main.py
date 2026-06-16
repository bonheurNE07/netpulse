import sys
import os
import asyncio
import ipaddress
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.align import Align
from rich import box

from netpulse.discovery.services.discovery import DiscoveryService
from netpulse.discovery.models.discovery import DiscoveryMethod
from netpulse.discovery.models.device import DeviceStatus
from netpulse.core.services.db import DatabaseService
from netpulse.discovery.services.drift import DriftService
from netpulse.discovery.models.drift import DriftResult

# Initialize persistent SQLite storage & drift services
db_service = DatabaseService("netpulse.db")
drift_service = DriftService()


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
    ports: Optional[str] = typer.Option(
        None,
        "--ports",
        "-p",
        help="TCP port(s) to scan on active hosts (e.g. '22,80,443' or 'common' for standard presets).",
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

    # 1.5. Parse and validate port scanning options
    parsed_ports = None
    if ports:
        if ports.lower() == "common":
            # Preset common ports list (Top 20 most scanned ports)
            parsed_ports = [21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445, 993, 995, 1433, 3306, 3389, 5900, 8080, 8443]
        else:
            try:
                parsed_ports = []
                for p in ports.split(","):
                    p_stripped = p.strip()
                    if p_stripped:
                        port_val = int(p_stripped)
                        if 1 <= port_val <= 65535:
                            parsed_ports.append(port_val)
                        else:
                            raise ValueError(f"Port '{port_val}' is outside valid TCP range (1-65535).")
                if not parsed_ports:
                    raise ValueError("No ports found in specified list.")
            except ValueError as ve:
                console.print(Panel(
                    f"[bold red]Error:[/] Invalid port scanning arguments.\n"
                    f"[yellow]Details:[/] {ve}\n\n"
                    f"[bold green]Examples of valid inputs:[/]\n"
                    f"  • [bold white]-p 22,80,443[/]\n"
                    f"  • [bold white]--ports common[/] (to scan top 20 standard ports)",
                    title="[bold red]Port Validation Error[/bold red]",
                    border_style="red",
                    box=box.ROUNDED,
                ))
                raise typer.Exit(code=1)

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
                interface=interface,
                ports=parsed_ports
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
        
        # Include Open Ports column if port scanning was executed
        if parsed_ports:
            table.add_column("Open Ports (Services)", style="yellow", justify="left")

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

            row_data = [
                str(device.ip),
                mac_str,
                rtt_str,
                status_str,
                vendor_str
            ]
            
            if parsed_ports:
                open_ports = device.metadata.get("open_ports", [])
                if open_ports:
                    ports_str = ", ".join(f"[bold green]{p['port']}[/]({p['service'].lower()})" for p in open_ports)
                else:
                    ports_str = "[dim white]none[/]"
                row_data.append(ports_str)

            table.add_row(*row_data)

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

    # Automatically persist completed sweeps to local SQLite history
    try:
        db_service.save_scan(result)
    except Exception:
        pass

    # Exit code based on status
    if result.status == "failed":
        raise typer.Exit(code=1)
    elif result.status == "partial":
        raise typer.Exit(code=2)
    raise typer.Exit(code=0)

@app.command(name="version", help="Show NetPulse version information.")
def version():
    """Prints the CLI and package version details."""
    console.print("[bold magenta]NetPulse CLI[/bold magenta] version [bold cyan]0.1.0.4[/bold cyan]")

try:
    from netpulse.subnet.cli import app as subnet_app
    app.add_typer(subnet_app, name="subnet")
except ImportError:
    pass

# -------------------------------------------------------------
# Storage & Network Drift CLI Commands
# -------------------------------------------------------------
def render_drift(result: DriftResult):
    # 1. Summary Header
    summary_text = (
        f"[bold cyan]Target Subnet :[/] [white]{result.network}[/]\n"
        f"[bold cyan]Baseline Scan :[/] [white]{result.old_timestamp.replace('T', ' ')[:19] if result.old_timestamp else 'N/A'}[/] [dim white]({str(result.old_scan_id)[:8] + '...' if result.old_scan_id else 'None'})[/]\n"
        f"[bold cyan]Current Sweep :[/] [white]{result.new_timestamp.replace('T', ' ')[:19]}[/] [dim white]({str(result.new_scan_id)[:8] + '...'})[/]"
    )
    console.print(Panel(
        Align.center(summary_text),
        title="[bold magenta]⚡ Network Drift Analysis Summary ⚡[/bold magenta]",
        border_style="magenta",
        box=box.DOUBLE,
    ))

    # 2. Joined Devices (Green)
    if result.joined:
        table_joined = Table(box=box.ROUNDED, header_style="bold green", border_style="green", title="[bold green]Devices Joined (Newly Online) ✔[/bold green]")
        table_joined.add_column("IP Address", style="bold green")
        table_joined.add_column("MAC Address", style="white")
        table_joined.add_column("Latency", style="yellow", justify="right")
        table_joined.add_column("Vendor", style="dim green")
        for d in result.joined:
            mac_str = d.mac if d.mac else "N/A"
            rtt_str = f"{d.rtt_ms:.3f} ms" if d.rtt_ms is not None else "N/A"
            vendor_str = d.vendor if d.vendor else "-"
            table_joined.add_row(str(d.ip), mac_str, rtt_str, vendor_str)
        console.print(table_joined)

    # 3. Left Devices (Red)
    if result.left:
        table_left = Table(box=box.ROUNDED, header_style="bold red", border_style="red", title="[bold red]Devices Left (Offline or Missing) ✖[/bold red]")
        table_left.add_column("IP Address", style="bold red")
        table_left.add_column("MAC Address", style="dim white")
        table_left.add_column("Vendor", style="dim red")
        for d in result.left:
            mac_str = d.mac if d.mac else "N/A"
            vendor_str = d.vendor if d.vendor else "-"
            table_left.add_row(str(d.ip), mac_str, vendor_str)
        console.print(table_left)

    # 4. Modified Devices (Yellow)
    if result.modified:
        table_mod = Table(box=box.ROUNDED, header_style="bold yellow", border_style="yellow", title="[bold yellow]Devices Modified (Configuration Changed) ⚠️[/bold yellow]")
        table_mod.add_column("IP Address", style="bold yellow")
        table_mod.add_column("Previous MAC", style="dim white")
        table_mod.add_column("New MAC", style="white")
        table_mod.add_column("Previous Latency", style="dim white", justify="right")
        table_mod.add_column("New Latency", style="yellow", justify="right")
        for c in result.modified:
            mac_old = c.mac_old if c.mac_old else "N/A"
            mac_new = c.mac_new if c.mac_new else "N/A"
            rtt_old = f"{c.rtt_old:.3f} ms" if c.rtt_old is not None else "N/A"
            rtt_new = f"{c.rtt_new:.3f} ms" if c.rtt_new is not None else "N/A"
            
            # Highlight MAC reassignment as warning
            mac_display_new = f"[bold red]{mac_new}[/]" if c.mac_old != c.mac_new else mac_new
            table_mod.add_row(c.ip, mac_old, mac_display_new, rtt_old, rtt_new)
        console.print(table_mod)

    # 5. Unchanged summary
    if result.unchanged:
        console.print(f"[dim white]• {len(result.unchanged)} device(s) remained unchanged and active since baseline.[/dim white]\n")
    
    # 6. Overall stats
    if not result.joined and not result.left and not result.modified:
        console.print(Panel(
            Align.center("[bold green]Zero changes detected. Subnet state is perfectly stable! ✔[/bold green]"),
            border_style="green",
            box=box.ROUNDED
        ))


@app.command(name="discover-history", help="Query all past discovery scan summaries.")
def discover_history(
    network: Optional[str] = typer.Argument(
        None,
        help="Filter scan histories by target subnet CIDR (e.g. 192.168.1.0/24)."
    )
):
    if network:
        try:
            ipaddress.ip_network(network, strict=False)
        except ValueError as e:
            console.print(Panel(
                f"[bold red]Validation Error:[/] Invalid CIDR network '[yellow]{network}[/]'.\nDetails: {e}",
                border_style="red",
                box=box.ROUNDED,
            ))
            raise typer.Exit(code=1)

    with console.status("[bold cyan]Retrieving history...[/bold cyan]"):
        history = db_service.get_scan_history(network)

    if not history:
        console.print(Panel(
            "[bold yellow]No historic scans found in the local database.[/bold yellow]\nRun [bold cyan]netpulse discover <target>[/] first.",
            title="[bold yellow]No History[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=0)

    table = Table(
        box=box.ROUNDED,
        header_style="bold magenta",
        border_style="cyan",
        title="Discovery Scans History",
        title_style="bold cyan underline"
    )
    table.add_column("Scan ID", style="dim white", justify="left")
    table.add_column("Target Subnet", style="bold cyan", justify="left")
    table.add_column("Status", justify="center")
    table.add_column("Active Hosts", style="bold green", justify="right")
    table.add_column("Total Subnet IPs", style="yellow", justify="right")
    table.add_column("Started At (UTC)", style="white", justify="left")
    table.add_column("Protocols", style="dim white", justify="left")

    for row in history:
        status_str = "[bold green]COMPLETED ●[/]" if row["status"] == "completed" else "[bold yellow]PARTIAL ▲[/]" if row["status"] == "partial" else "[bold red]FAILED ■[/]"
        table.add_row(
            str(row["id"])[:8] + "...",
            row["network"],
            status_str,
            str(row["responsive_count"]),
            str(row["scanned_count"]),
            row["started_at"].replace("T", " ")[:19],
            ", ".join(row["methods"]).upper()
        )
    console.print(table)


@app.command(name="discover-drift", help="Scan a network and instantly analyze change drift against baseline history.")
def discover_drift(
    target: str = typer.Argument(
        ...,
        help="Target CIDR network address range to sweep (e.g. 192.168.1.0/24).",
    ),
    methods: Optional[List[str]] = typer.Option(
        None,
        "--method",
        "-m",
        help="Discovery protocol(s) to use: arp, icmp. Defaults to arp.",
    ),
    timeout: int = typer.Option(
        1000,
        "--timeout",
        "-t",
        help="Timeout in milliseconds for responses.",
    ),
    interface: Optional[str] = typer.Option(
        None,
        "--interface",
        "-i",
        help="Explicit network interface to sweep on (Ony used by ARP).",
    )
):
    # 1. Validate target CIDR network
    try:
        ipaddress.ip_network(target, strict=False)
    except ValueError as e:
        console.print(Panel(
            f"[bold red]Error:[/] Invalid target network CIDR '[yellow]{target}[/]'.\nDetails: {e}",
            title="[bold red]Malformed Target Range[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    # 2. Fetch baseline scan from SQLite
    try:
        baseline = db_service.get_latest_scan(target)
    except Exception as db_err:
        console.print(Panel(f"Failed to fetch baseline scan: {db_err}", border_style="yellow"))
        baseline = None

    # 3. Parse and validate methods
    valid_methods = {"arp": DiscoveryMethod.ARP, "icmp": DiscoveryMethod.ICMP}
    parsed_methods = []
    if not methods:
        parsed_methods = [DiscoveryMethod.ARP]
    else:
        for m in methods:
            m_lower = m.lower()
            if m_lower not in valid_methods:
                console.print(Panel(
                    f"[bold red]Error:[/] Invalid discovery method '[yellow]{m}[/]'.\nSupported: arp, icmp.",
                    border_style="red",
                    box=box.ROUNDED,
                ))
                raise typer.Exit(code=1)
            parsed_methods.append(valid_methods[m_lower])

    # 4. Execute new sweep
    with console.status(
        f"[bold cyan]Sweeping network [magenta]{target}[/] for drift updates...[/bold cyan]",
        spinner="dots"
    ):
        try:
            service = DiscoveryService()
            new_result = asyncio.run(service.discover_network(
                target_network=target,
                methods=parsed_methods,
                timeout_ms=timeout,
                interface=interface
            ))
        except Exception as e:
            console.print(Panel(
                f"[bold red]Sweep Failed Unhandled Exception:[/] {e}",
                border_style="red",
                box=box.ROUNDED,
            ))
            raise typer.Exit(code=1)

    # Handle permission errors
    is_permission_error = False
    for err in new_result.errors:
        if "permission denied" in err.lower() or "operation not permitted" in err.lower():
            is_permission_error = True
            break

    if is_permission_error:
        console.print(Panel(
            "[bold red]Privileges Required:[/] NetPulse requires elevated raw socket capabilities.\nRun with sudo or grant setcap.",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    # 5. Calculate drift comparison
    try:
        drift_res = drift_service.calculate_drift(new_result, baseline)
    except Exception as e:
        console.print(Panel(
            f"[bold red]Drift Calculation Failed:[/] {e}",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    # 6. Render comparison visual panels
    render_drift(drift_res)

    # 7. Persist new scan in SQLite database
    try:
        db_service.save_scan(new_result)
    except Exception:
        pass


@app.command(name="discover-compare", help="Compare two specific historic sweeps by their Scan UUIDs.")
def discover_compare(
    scan_id_old: str = typer.Argument(
        ...,
        help="Scan UUID of the baseline scan."
    ),
    scan_id_new: str = typer.Argument(
        ...,
        help="Scan UUID of the comparison target scan."
    )
):
    with console.status("[bold cyan]Loading scan details from SQLite...[/bold cyan]"):
        try:
            old_scan = db_service.get_scan(scan_id_old)
            if not old_scan:
                console.print(Panel(f"Baseline scan with UUID '[yellow]{scan_id_old}[/]' not found.", border_style="red"))
                raise typer.Exit(code=1)

            new_scan = db_service.get_scan(scan_id_new)
            if not new_scan:
                console.print(Panel(f"Comparison scan with UUID '[yellow]{scan_id_new}[/]' not found.", border_style="red"))
                raise typer.Exit(code=1)

            drift_res = drift_service.calculate_drift(new_scan, old_scan)
        except Exception as e:
            console.print(Panel(f"Failed to calculate compare drift: {e}", border_style="red"))
            raise typer.Exit(code=1)

    render_drift(drift_res)


try:
    from netpulse.ssh.cli import app as ssh_app
    app.add_typer(ssh_app, name="ssh")
except ImportError:
    pass

if __name__ == "__main__":
    app()
