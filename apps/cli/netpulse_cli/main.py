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
from netpulse_core.services.subnet import (
    calculate_subnet_info,
    split_fixed_length,
    allocate_vlsm,
    find_containing_subnet
)
from netpulse_core.services.db import DatabaseService
from netpulse_core.services.drift import DriftService
from netpulse_core.models.drift import DriftResult
from netpulse_core.models.ssh import SshHostConfig, SshStatus
from netpulse_core.services.ssh_runner import SshRunnerService

# Initialize persistent SQLite storage & drift services
db_service = DatabaseService("netpulse.db")
drift_service = DriftService()
ssh_runner = SshRunnerService(db_service)

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
    console.print("[bold magenta]NetPulse CLI[/bold magenta] version [bold cyan]0.1.0[/bold cyan]")

# -------------------------------------------------------------
# Subnetting & VLSM Commands
# -------------------------------------------------------------

subnet_app = typer.Typer(
    name="subnet",
    help="Subnetting & VLSM calculation suite for network engineers.",
    no_args_is_help=True,
)

@subnet_app.command(name="info", help="Calculate network boundaries and display bitwise binary alignments.")
def subnet_info(
    ip_or_cidr: str = typer.Argument(
        ...,
        help="IP address with optional mask/prefix (e.g. 192.168.1.50/24 or 192.168.1.50/255.255.255.0)."
    ),
    mask: Optional[str] = typer.Option(
        None,
        "--mask",
        "-m",
        help="Subnet mask or prefix length if not specified in the CIDR argument (e.g., 255.255.255.0 or 24)."
    )
):
    # Parse IP and mask
    if "/" in ip_or_cidr:
        parts = ip_or_cidr.split("/", 1)
        ip = parts[0].strip()
        mask_val = parts[1].strip()
        if mask is not None:
            console.print(Panel(
                f"[bold yellow]Warning:[/] Mask specified in both CIDR and --mask option. Using CIDR mask '[bold cyan]{mask_val}[/]'.",
                border_style="yellow",
                box=box.ROUNDED,
            ))
    else:
        ip = ip_or_cidr.strip()
        if mask is None:
            mask_val = "32"  # default to single host
        else:
            mask_val = mask.strip()

    try:
        # Validate IP structure first
        ipaddress.ip_address(ip)
    except ValueError as e:
        console.print(Panel(
            f"[bold red]Error:[/] Invalid IP address '[yellow]{ip}[/]'.\nDetails: {e}",
            title="[bold red]Validation Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    try:
        info = calculate_subnet_info(ip, mask_val)
    except Exception as e:
        console.print(Panel(
            f"[bold red]Error calculating subnet info:[/] {e}",
            title="[bold red]Calculation Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    # Render results beautifully
    # 1. Summary Grid
    details_table = Table(box=box.SIMPLE, show_header=False, min_width=50)
    details_table.add_column("Property", style="bold cyan", justify="right")
    details_table.add_column("Value", style="white", justify="left")

    details_table.add_row("IP Address Queried", str(info.ip))
    details_table.add_row("Network CIDR Range", info.network_cidr)
    details_table.add_row("Network Address", str(info.network_address))
    details_table.add_row("Subnet Netmask", f"{info.netmask} (/{info.prefix_length})")
    details_table.add_row("Wildcard Mask", str(info.wildcard_mask))
    details_table.add_row("Broadcast Address", str(info.broadcast_address))
    
    if info.first_usable and info.last_usable:
        details_table.add_row("Usable IP Range", f"{info.first_usable} — {info.last_usable}")
    else:
        details_table.add_row("Usable IP Range", "N/A")
        
    details_table.add_row("Total Usable Hosts", f"{info.total_hosts:,} host(s)")

    # 2. Binary Bitwise Alignment
    # Determine version (IPv4 vs IPv6)
    version = 4 if "." in str(info.ip) else 6
    
    def format_binary(binary_str: str, prefix_len: int, ver: int) -> str:
        sep = "." if ver == 4 else ":"
        bits_only = binary_str.replace(sep, "")
        
        bits_colored = []
        for idx, bit in enumerate(bits_only):
            if idx < prefix_len:
                bits_colored.append(f"[bold cyan]{bit}[/bold cyan]")
            else:
                bits_colored.append(f"[bold magenta]{bit}[/bold magenta]")
                
        chunk_size = 8 if ver == 4 else 16
        parts = []
        for idx in range(0, len(bits_colored), chunk_size):
            parts.append("".join(bits_colored[idx:idx+chunk_size]))
        return sep.join(parts)

    bin_ip = format_binary(info.binary_representation.get("ip", ""), info.prefix_length, version)
    bin_mask = format_binary(info.binary_representation.get("netmask", ""), info.prefix_length, version)
    bin_net = format_binary(info.binary_representation.get("network", ""), info.prefix_length, version)

    # Construct the binary alignment layout
    binary_layout = Table(box=box.SIMPLE, show_header=False)
    binary_layout.add_column("Type", style="bold yellow", justify="right")
    binary_layout.add_column("Binary Alignment", justify="left")
    binary_layout.add_column("Decimal/Hex", style="dim white", justify="left")

    binary_layout.add_row("IP Bits", bin_ip, f"({info.ip})")
    binary_layout.add_row("Mask Bits", bin_mask, f"({info.netmask})")
    binary_layout.add_row("Net Bits", bin_net, f"({info.network_address})")

    # Legend
    legend = (
        "[bold cyan]■ Network Bits[/bold cyan]    "
        "[bold magenta]■ Host Bits[/bold magenta]"
    )

    # Render parent panel
    console.print(Panel(
        Align.center(details_table),
        title=f"[bold magenta]🌐 Subnet Parameters: {info.network_cidr} [/bold magenta]",
        border_style="magenta",
        box=box.ROUNDED,
    ))

    from rich.console import Group
    console.print(Panel(
        Group(
            Align.center(binary_layout),
            Align.center(""),
            Align.center(legend)
        ),
        title="[bold yellow]🔢 Bitwise Binary Alignment [/bold yellow]",
        border_style="yellow",
        box=box.ROUNDED,
    ))


@subnet_app.command(name="split", help="Split a parent network into equal-sized FLSM subnets.")
def subnet_split(
    parent_network: str = typer.Argument(
        ...,
        help="Parent CIDR network to partition (e.g. 10.0.0.0/8 or 192.168.1.0/24)."
    ),
    subnets: Optional[int] = typer.Option(
        None,
        "--subnets",
        "-s",
        help="Divide parent network into exactly N subnets."
    ),
    hosts: Optional[int] = typer.Option(
        None,
        "--hosts",
        "-h",
        help="Divide parent network into subnets accommodating at least M usable hosts each."
    )
):
    if subnets is None and hosts is None:
        console.print(Panel(
            "[bold red]Validation Error:[/] You must specify either [bold yellow]--subnets (-s)[/] or [bold yellow]--hosts (-h)[/].",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)
        
    if subnets is not None and hosts is not None:
        console.print(Panel(
            "[bold red]Validation Error:[/] You cannot specify both [bold yellow]--subnets (-s)[/] and [bold yellow]--hosts (-h)[/]. Please choose one.",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    try:
        split_cidr_list = split_fixed_length(parent_network, subnets_count=subnets, hosts_per_subnet=hosts)
    except Exception as e:
        console.print(Panel(
            f"[bold red]Error splitting network:[/] {e}",
            title="[bold red]Partitioning Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    # Render partitions table
    table = Table(
        box=box.ROUNDED,
        header_style="bold magenta",
        border_style="cyan",
        title=f"Equal Partition Split: {parent_network}",
        title_style="bold cyan underline"
    )
    table.add_column("Subnet #", style="bold yellow", justify="center")
    table.add_column("Network CIDR", style="bold cyan", justify="left")
    table.add_column("Netmask", style="white", justify="left")
    table.add_column("Usable IP Range", style="green", justify="left")
    table.add_column("Broadcast IP", style="white", justify="left")
    table.add_column("Total Hosts", style="yellow", justify="right")

    for idx, cidr in enumerate(split_cidr_list, start=1):
        try:
            info = calculate_subnet_info(cidr.split("/")[0], cidr.split("/")[1])
            usable_range = f"{info.first_usable} — {info.last_usable}" if info.first_usable else "N/A"
            table.add_row(
                str(idx),
                info.network_cidr,
                str(info.netmask),
                usable_range,
                str(info.broadcast_address),
                f"{info.total_hosts:,}"
            )
        except Exception:
            table.add_row(str(idx), cidr, "-", "-", "-", "-")

    console.print(table)


@subnet_app.command(name="vlsm", help="Allocate optimal subnets for varying host sizes using VLSM.")
def subnet_vlsm(
    parent_network: str = typer.Argument(
        ...,
        help="Parent IPv4 CIDR range (e.g. 192.168.1.0/24)."
    ),
    req: str = typer.Option(
        ...,
        "--req",
        "-r",
        help="Comma-separated list of Name=Hosts requirements (e.g. 'HR=120,Dev=50,Sales=20,Links=2')."
    )
):
    # Parse requirements
    requirements = []
    for item in req.split(","):
        if not item.strip():
            continue
        if "=" not in item:
            console.print(Panel(
                f"[bold red]Format Error:[/] Requirement '[yellow]{item}[/]' must be in key=value format (e.g. HR=50).",
                border_style="red",
                box=box.ROUNDED,
            ))
            raise typer.Exit(code=1)
        name, hosts_str = item.split("=", 1)
        name = name.strip()
        try:
            hosts = int(hosts_str.strip())
            if hosts <= 0:
                raise ValueError()
        except ValueError:
            console.print(Panel(
                f"[bold red]Validation Error:[/] Hosts count for '[yellow]{name}[/]' must be a positive integer, got '[red]{hosts_str}[/]'.",
                border_style="red",
                box=box.ROUNDED,
            ))
            raise typer.Exit(code=1)
        requirements.append({"name": name, "hosts": hosts})

    try:
        result = allocate_vlsm(parent_network, requirements)
    except Exception as e:
        console.print(Panel(
            f"[bold red]VLSM Allocation Failed:[/] {e}",
            title="[bold red]Allocation Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    # 1. Success table
    table = Table(
        box=box.ROUNDED,
        header_style="bold magenta",
        border_style="cyan",
        title=f"VLSM Address Allocation: {parent_network}",
        title_style="bold cyan underline"
    )
    table.add_column("Subnet Name", style="bold yellow", justify="left")
    table.add_column("Req Hosts", style="white", justify="right")
    table.add_column("Allocated", style="white", justify="right")
    table.add_column("Network CIDR", style="bold cyan", justify="left")
    table.add_column("Netmask", style="dim white", justify="left")
    table.add_column("Usable IP Range", style="green", justify="left")
    table.add_column("Broadcast IP", style="dim white", justify="left")
    table.add_column("Wastage %", justify="right")

    for alloc in result.allocations:
        # Determine color for wastage
        if alloc.wastage_percent > 50:
            wastage_style = f"[bold red]{alloc.wastage_percent:.1f}%[/]"
        elif alloc.wastage_percent > 30:
            wastage_style = f"[bold yellow]{alloc.wastage_percent:.1f}%[/]"
        else:
            wastage_style = f"[bold green]{alloc.wastage_percent:.1f}%[/]"

        table.add_row(
            alloc.name,
            str(alloc.hosts_requested),
            str(alloc.hosts_allocated),
            alloc.network_cidr,
            alloc.netmask,
            f"{alloc.first_usable} — {alloc.last_usable}",
            alloc.broadcast,
            wastage_style
        )

    console.print(table)

    # 2. Warnings / Unallocated requirements
    if result.unallocated_requirements:
        unallocated_table = Table(
            box=box.ROUNDED,
            header_style="bold red",
            border_style="red",
            title="UNSATISFIED REQUIREMENTS (Out of address space)",
            title_style="bold red underline"
        )
        unallocated_table.add_column("Requirement Name", style="bold white", justify="left")
        unallocated_table.add_column("Requested Hosts", style="yellow", justify="right")

        for req_un in result.unallocated_requirements:
            unallocated_table.add_row(req_un.name, str(req_un.hosts))

        console.print(unallocated_table)

    # 3. Free pool left
    if result.free_space_remaining:
        free_table = Table(
            box=box.ROUNDED,
            header_style="bold green",
            border_style="green",
            title="Available Unallocated Blocks",
            title_style="bold green underline"
        )
        free_table.add_column("Block CIDR", style="bold green", justify="left")
        free_table.add_column("Netmask", style="white", justify="left")
        free_table.add_column("Total Host Capacity", style="yellow", justify="right")

        for block in result.free_space_remaining:
            try:
                # Get total capacity
                net = ipaddress.ip_network(block)
                cap = net.num_addresses - 2 if net.prefixlen < 31 else net.num_addresses
                free_table.add_row(block, str(net.netmask), f"{cap:,}")
            except Exception:
                free_table.add_row(block, "-", "-")

        console.print(free_table)


@subnet_app.command(name="discover", help="Discover which subnet an IP address belongs to from a given list.")
def subnet_discover(
    ip: str = typer.Argument(
        ...,
        help="IP address to locate (e.g. 192.168.1.45)."
    ),
    subnets: str = typer.Option(
        ...,
        "--subnets",
        "-s",
        help="Comma-separated list of candidate CIDR network subnets (e.g. '192.168.1.0/26,192.168.1.64/26')."
    )
):
    try:
        # Validate target IP
        ipaddress.ip_address(ip)
    except ValueError as e:
        console.print(Panel(
            f"[bold red]Error:[/] Invalid IP address '[yellow]{ip}[/]'.\nDetails: {e}",
            title="[bold red]Validation Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    subnet_list = [s.strip() for s in subnets.split(",") if s.strip()]
    
    # Pre-validate subnets lists to be helpful
    cleaned_subnets = []
    malformed = []
    for s in subnet_list:
        try:
            ipaddress.ip_network(s, strict=False)
            cleaned_subnets.append(s)
        except ValueError:
            malformed.append(s)

    if malformed:
        console.print(Panel(
            f"[bold yellow]Warning:[/] Skipping the following malformed subnet(s):\n" + 
            "\n".join([f" • [red]{m}[/]" for m in malformed]),
            border_style="yellow",
            box=box.ROUNDED,
        ))

    if not cleaned_subnets:
        console.print(Panel(
            "[bold red]Error:[/] No valid CIDR subnets were provided to match against.",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    with console.status("[bold cyan]Searching candidate subnets...[/bold cyan]"):
        matched = find_containing_subnet(ip, cleaned_subnets)

    if matched:
        # Retrieve detailed info to wow the user
        try:
            info = calculate_subnet_info(ip, matched.split("/")[1])
            success_text = (
                f"[bold green]Match Discovered! ✔[/bold green]\n\n"
                f"IP address [bold yellow]{ip}[/] belongs to subnet [bold cyan]{matched}[/].\n\n"
                f"[bold white]Subnet Details:[/]\n"
                f"  • [bold cyan]Network CIDR    :[/] [white]{info.network_cidr}[/]\n"
                f"  • [bold cyan]Usable IP Range :[/] [white]{info.first_usable} — {info.last_usable}[/]\n"
                f"  • [bold cyan]Broadcast IP    :[/] [white]{info.broadcast_address}[/]\n"
                f"  • [bold cyan]Capacity        :[/] [white]{info.total_hosts} usable hosts[/]"
            )
            console.print(Panel(
                success_text,
                title="[bold green]Subnet Discovered[/bold green]",
                border_style="green",
                box=box.ROUNDED,
            ))
        except Exception:
            console.print(Panel(
                f"[bold green]Match Discovered! ✔[/bold green]\n\nIP address [bold yellow]{ip}[/] belongs to subnet [bold cyan]{matched}[/].",
                title="[bold green]Subnet Discovered[/bold green]",
                border_style="green",
                box=box.ROUNDED,
            ))
    else:
        console.print(Panel(
            f"[bold red]No Match Found ✖[/bold red]\n\nIP address [bold yellow]{ip}[/] does not belong to any of the candidate subnets.",
            title="[bold red]Lookup Failed[/bold red]",
            border_style="red",
            box=box.ROUNDED,
            ))
        raise typer.Exit(code=1)


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


# SSH Command Group
ssh_app = typer.Typer(
    help="NetPulse SSH: Intelligent, high-speed configuration and execution engine for network devices.",
    no_args_is_help=True
)

@ssh_app.command(name="run", help="Concurrently execute diagnostic or configuration commands across network devices.")
def ssh_run(
    targets_input: str = typer.Argument(
        ...,
        metavar="HOSTS",
        help="Target IPs (comma-separated, e.g. 192.168.1.5,192.168.1.20) or CIDR block (e.g. 192.168.1.0/24)."
    ),
    command: str = typer.Argument(
        ...,
        help="Command string to execute (e.g., 'show ip interface brief')."
    ),
    username: str = typer.Option(
        ...,
        "--username",
        "-u",
        help="SSH login username."
    ),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        "-p",
        help="SSH login password. Will prompt securely if omitted.",
        prompt=True,
        hide_input=True
    ),
    enable_password: Optional[str] = typer.Option(
        None,
        "--enable-password",
        "-e",
        help="Cisco privilege exec mode password (optional). Will prompt securely if specified without password.",
        hide_input=True
    ),
    port: int = typer.Option(
        22,
        "--port",
        help="SSH port."
    ),
    auto_negotiate: bool = typer.Option(
        True,
        "--auto-negotiate/--no-auto-negotiate",
        help="Enable dynamic legacy key-exchange and cipher fallbacks."
    ),
    ignore_host_keys: bool = typer.Option(
        True,
        "--ignore-host-keys/--no-ignore-host-keys",
        help="Bypass SSH Strict Host Key verification checking."
    ),
    timeout: int = typer.Option(
        10,
        "--timeout",
        "-t",
        help="Connection timeout in seconds."
    )
):
    # Parse target hosts
    hosts_list = []
    is_cidr = False
    try:
        ipaddress.ip_network(targets_input, strict=False)
        is_cidr = True
    except ValueError:
        pass
        
    if is_cidr:
        # Check latest completed scan in SQLite for this network block
        latest = db_service.get_latest_scan(targets_input)
        if latest and latest.devices:
            # Gather all active IPs
            hosts_list = [str(dev.ip) for dev in latest.devices if dev.status == "up"]
            if not hosts_list:
                console.print(Panel(
                    f"[bold yellow]Warning:[/] No active/up hosts found in local database history for subnet [bold cyan]{targets_input}[/].\n"
                    f"Please run [bold green]netpulse discover {targets_input}[/] first to discover alive hosts.",
                    title="[bold yellow]No Targets Found[/bold yellow]",
                    border_style="yellow"
                ))
                raise typer.Exit(code=1)
        else:
            console.print(Panel(
                f"[bold red]Error:[/] No historical scans found for subnet [bold cyan]{targets_input}[/] in the local database.\n"
                f"Please execute [bold green]netpulse discover {targets_input}[/] first to map alive hosts, or specify individual IPs.",
                title="[bold red]Historical Map Missing[/bold red]",
                border_style="red"
            ))
            raise typer.Exit(code=1)
    else:
        # Simple split by commas
        hosts_list = [h.strip() for h in targets_input.split(",") if h.strip()]

    if not hosts_list:
        console.print(Panel("[bold red]Error:[/] No target hosts specified.", border_style="red"))
        raise typer.Exit(code=1)

    # Build SshHostConfig configurations
    configs = [
        SshHostConfig(
            ip=host,
            port=port,
            username=username,
            password=password,
            enable_password=enable_password,
            auto_negotiate=auto_negotiate,
            ignore_host_keys=ignore_host_keys,
            timeout_seconds=timeout
        )
        for host in hosts_list
    ]

    console.print(f"\n[bold cyan]Preparing to execute SSH command '[magenta]{command}[/]' concurrently across {len(configs)} host(s)...[/bold cyan]\n")

    # Run executing concurrently with a beautiful Rich spinner
    with console.status("[bold green]Executing concurrent SSH sweeps...[/bold green]", spinner="dots"):
        try:
            audit = asyncio.run(ssh_runner.execute_concurrently(configs, command))
        except Exception as e:
            console.print(Panel(f"[bold red]Execution Failure:[/] {e}", title="[bold red]System Error[/bold red]", border_style="red"))
            raise typer.Exit(code=1)

    # Render results table
    table = Table(
        title="⚡ NetPulse SSH Multi-Host Execution Summary ⚡",
        title_style="bold cyan",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta"
    )
    table.add_column("IP Address", style="bold white", justify="left")
    table.add_column("Status", justify="center")
    table.add_column("Latency (RTT)", justify="right")
    table.add_column("Negotiated KEX", justify="left", style="dim")
    table.add_column("Negotiated Cipher", justify="left", style="dim")
    table.add_column("Diagnostics / Failure Details", justify="left")

    for res in audit.results:
        lat = f"{res.latency_ms:.2f} ms" if res.latency_ms is not None else "N/A"
        
        if res.status == SshStatus.SUCCESS:
            status_str = "[bold green]✔ SUCCESS[/bold green]"
            details = "[dim]Standard handshake[/dim]"
            if res.negotiated_kex and ("sha1" in res.negotiated_kex or "3des" in res.negotiated_cipher or "cbc" in res.negotiated_cipher):
                details = "[bold yellow]⚠ Healed Legacy Handshake[/bold yellow]"
        else:
            status_str = "[bold red]✘ FAILED[/bold red]"
            details = f"[red]{res.error_message}[/red]"

        table.add_row(
            res.ip,
            status_str,
            lat,
            res.negotiated_kex or "N/A",
            res.negotiated_cipher or "N/A",
            details
        )

    console.print(table)
    console.print(f"\n[bold green]Concurrent executions finished:[/] {audit.success_count} succeeded, {audit.failed_count} failed.\n")

    # Display outputs of successful runs
    for res in audit.results:
        if res.status == SshStatus.SUCCESS and res.stdout:
            output_clean = res.stdout.strip()
            console.print(Panel(
                Syntax(output_clean, "text", theme="monokai", background_color="default"),
                title=f"[bold green]✔ Host Output: {res.ip}[/bold green]",
                border_style="green",
                box=box.ROUNDED
            ))
            console.print()

@ssh_app.command(name="history", help="Query basic logs for all past concurrent SSH executions.")
def ssh_history():
    """
    Displays the persistent history of all multi-host SSH audits.
    """
    history = db_service.get_ssh_history()
    if not history:
        console.print("\n[bold yellow]No historic SSH executions found in the local database.[/bold yellow]\n")
        raise typer.Exit(code=0)

    table = Table(
        title="⚡ NetPulse SSH Operations Audit History ⚡",
        title_style="bold cyan",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta"
    )
    table.add_column("Session UUID", style="dim", justify="left")
    table.add_column("Command Executed", style="bold white", justify="left")
    table.add_column("Targets Count", justify="center")
    table.add_column("Succeeded", style="green", justify="center")
    table.add_column("Failed", style="red", justify="center")
    table.add_column("Executed At (UTC)", justify="left")

    for audit in history:
        table.add_row(
            audit["id"][:8] + "...",
            audit["command"],
            str(len(audit["targets"])),
            str(audit["success_count"]),
            str(audit["failed_count"]),
            audit["executed_at"]
        )

    console.print(table)


# Register Typer command groups
app.add_typer(subnet_app, name="subnet")
app.add_typer(ssh_app, name="ssh")

if __name__ == "__main__":
    app()
