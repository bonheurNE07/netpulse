import typer
import ipaddress
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich import box

from netpulse.subnet.services.subnet import (
    calculate_subnet_info,
    split_fixed_length,
    allocate_vlsm,
    find_containing_subnet
)

console = Console()

# -------------------------------------------------------------
# Subnetting & VLSM Commands
# -------------------------------------------------------------

app = typer.Typer(
    name="subnet",
    help="Subnetting & VLSM calculation suite for network engineers.",
    no_args_is_help=True,
)

@app.command(name="info", help="Calculate network boundaries and display bitwise binary alignments.")
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


@app.command(name="split", help="Split a parent network into equal-sized FLSM subnets.")
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


@app.command(name="vlsm", help="Allocate optimal subnets for varying host sizes using VLSM.")
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


@app.command(name="discover", help="Discover which subnet an IP address belongs to from a given list.")
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


