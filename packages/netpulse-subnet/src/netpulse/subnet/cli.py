import typer
import ipaddress
import os
from typing import Optional, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich import box

from netpulse.subnet.services.subnet import (
    calculate_subnet_info,
    split_fixed_length,
    allocate_vlsm,
    find_containing_subnet,
    validate_subnets,
    summarize_subnets
)
from netpulse.subnet.services.ipam import (
    init_db,
    add_reservation,
    get_reservations,
    get_reservations_for_parent
)

console = Console()

# -------------------------------------------------------------
# Subnetting & VLSM Commands
# -------------------------------------------------------------

app = typer.Typer(
    help="Netpulse Subnet - Advanced IP math, VLSM, and validation tool.",
    no_args_is_help=True
)

ipam_app = typer.Typer(help="IP Address Management (IPAM) state tracking.", no_args_is_help=True)
app.add_typer(ipam_app, name="ipam")

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
    
    if info.broadcast_address:
        details_table.add_row("Broadcast Address", str(info.broadcast_address))
    else:
        details_table.add_row("Broadcast Address", "N/A (IPv6)")
    
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
        help="Number of hosts required per subnet (overhead automatically calculated)."
    ),
    commit: bool = typer.Option(
        False,
        "--commit",
        help="Commit these allocations to the local IPAM database."
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
        reserved = []
        if commit:
            try:
                reserved = get_reservations_for_parent(parent_network)
            except FileNotFoundError:
                console.print("[bold red]IPAM DB not found.[/] Run 'netpulse-subnet ipam init' first.")
                raise typer.Exit(1)
        
        split_cidr_list = split_fixed_length(parent_network, subnets_count=subnets, hosts_per_subnet=hosts, reserved_blocks=reserved)
        
        if commit:
            for s in split_cidr_list:
                add_reservation(s, f"Split from {parent_network}", parent_network)

    except Exception as e:
        console.print(Panel(
            f"[bold red]Error splitting network:[/] {e}",
            title="[bold red]Partitioning Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    if len(split_cidr_list) == 65536:
        console.print(Panel(
            "[bold yellow]Safety Truncation Activated:[/] The requested split generated a massive number of subnets (likely an IPv6 block). The output has been safely truncated to the first 65,536 subnets to prevent memory exhaustion.",
            title="[bold yellow]Output Truncated[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED,
        ))

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
                str(info.broadcast_address) if info.broadcast_address else "N/A",
                f"{info.total_hosts:,}"
            )
        except Exception:
            table.add_row(str(idx), cidr, "-", "-", "-", "-")

    console.print(table)
    if commit:
        console.print(f"[bold green]✔ Committed {len(split_cidr_list)} split blocks to IPAM database.[/bold green]")


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
    ),
    commit: bool = typer.Option(
        False,
        "--commit",
        help="Commit these allocations to the local IPAM database."
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
        reserved = []
        if commit:
            try:
                reserved = get_reservations_for_parent(parent_network)
            except FileNotFoundError:
                console.print("[bold red]IPAM DB not found.[/] Run 'netpulse-subnet ipam init' first.")
                raise typer.Exit(1)

        result = allocate_vlsm(parent_network, requirements, reserved_blocks=reserved)
        
        if commit:
            for alloc in result.allocations:
                add_reservation(alloc.network_cidr, alloc.name, parent_network)
                
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
            title="[bold red]UNSATISFIED REQUIREMENTS (Out of address space)[/bold red]",
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
    
    if commit:
        console.print(f"[bold green]✔ Committed {len(result.allocations)} VLSM blocks to IPAM database.[/bold green]")


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

@app.command(name="validate", help="Detect overlaps in a list of subnets and calculate remaining free space.")
def subnet_validate(
    subnets: List[str] = typer.Argument(
        None,
        help="List of CIDR network subnets to validate."
    ),
    file: Optional[str] = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to a text file containing one CIDR per line."
    ),
    parent: Optional[str] = typer.Option(
        None,
        "--parent",
        "-p",
        help="Optional parent network CIDR to calculate remaining unallocated free space."
    )
):
    all_subnets = []
    
    if subnets:
        all_subnets.extend(subnets)
        
    if file:
        if not os.path.exists(file):
            console.print(Panel(
                f"[bold red]Error:[/] File '[yellow]{file}[/]' does not exist.",
                border_style="red",
                box=box.ROUNDED,
            ))
            raise typer.Exit(code=1)
        with open(file, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    all_subnets.append(stripped)
                    
    if not all_subnets:
        console.print(Panel(
            "[bold red]Validation Error:[/] No subnets provided. Please provide subnets as arguments or via a --file.",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)
        
    try:
        result = validate_subnets(all_subnets, parent_network=parent)
    except Exception as e:
        console.print(Panel(
            f"[bold red]Validation Failed:[/] {e}",
            title="[bold red]Engine Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)
        
    # Render Output
    if result.has_overlaps:
        overlap_table = Table(
            box=box.ROUNDED,
            header_style="bold red",
            border_style="red",
            title="[bold red]CONFLICTS DETECTED[/bold red]",
            title_style="bold red underline"
        )
        overlap_table.add_column("Conflicting Subnet 1", style="bold yellow", justify="center")
        overlap_table.add_column("Conflicting Subnet 2", style="bold yellow", justify="center")
        
        for overlap in result.overlaps:
            overlap_table.add_row(overlap.subnet1, overlap.subnet2)
            
        console.print(overlap_table)
    else:
        console.print(Panel(
            f"[bold green]Validation Successful ✔[/bold green]\n\nZero overlaps detected across {len(all_subnets)} subnets.",
            title="[bold green]Clean Address Space[/bold green]",
            border_style="green",
            box=box.ROUNDED,
        ))
        
    if parent:
        if result.free_space:
            free_table = Table(
                box=box.ROUNDED,
                header_style="bold green",
                border_style="green",
                title=f"Available Unallocated Blocks in {parent}",
                title_style="bold green underline"
            )
            free_table.add_column("Block CIDR", style="bold cyan", justify="left")
            free_table.add_column("Total Host Capacity", style="white", justify="right")
            
            for block in result.free_space:
                try:
                    net = ipaddress.ip_network(block)
                    cap = net.num_addresses - 2 if net.prefixlen < 31 else net.num_addresses
                    free_table.add_row(block, f"{cap:,}")
                except:
                    free_table.add_row(block, "-")
            console.print(free_table)
        else:
            console.print(Panel(
                f"[bold yellow]Zero Free Space[/bold yellow]\n\nThe parent network [cyan]{parent}[/] is fully utilized.",
                border_style="yellow",
                box=box.ROUNDED,
            ))

@app.command(name="summarize", help="Summarize multiple subnets into the tightest encompassing CIDR block (Supernetting).")
def subnet_summarize(
    subnets: List[str] = typer.Argument(
        None,
        help="List of CIDR network subnets to summarize."
    ),
    file: Optional[str] = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to a text file containing one CIDR per line."
    )
):
    all_subnets = []
    
    if subnets:
        all_subnets.extend(subnets)
        
    if file:
        if not os.path.exists(file):
            console.print(Panel(
                f"[bold red]Error:[/] File '[yellow]{file}[/]' does not exist.",
                border_style="red",
                box=box.ROUNDED,
            ))
            raise typer.Exit(code=1)
        with open(file, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    all_subnets.append(stripped)
                    
    if not all_subnets:
        console.print(Panel(
            "[bold red]Validation Error:[/] No subnets provided. Please provide subnets as arguments or via a --file.",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)
        
    try:
        result = summarize_subnets(all_subnets)
    except Exception as e:
        console.print(Panel(
            f"[bold red]Summarization Failed:[/] {e}",
            title="[bold red]Engine Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        raise typer.Exit(code=1)

    table = Table(
        box=box.ROUNDED,
        header_style="bold cyan",
        border_style="cyan",
        title="[bold cyan]Route Summarization Result[/bold cyan]",
        title_style="bold cyan underline"
    )
    table.add_column("Property", style="bold yellow", justify="right")
    table.add_column("Value", style="white", justify="left")
    
    table.add_row("Encompassing Supernet", f"[bold green]{result.supernet}[/bold green]")
    table.add_row("Total Supernet IPs", f"{result.total_ips:,}")
    table.add_row("Explicitly Provided IPs", f"{result.provided_ips:,}")
    table.add_row("Slack (Unused) IPs", f"{result.slack_ips:,}")
    
    console.print(table)
    
    if result.has_slack:
        console.print(Panel(
            f"[bold yellow]⚠️ Slack Warning:[/] The calculated supernet encompasses [bold red]{result.slack_ips:,}[/] IP addresses that were NOT explicitly provided in your input list. Routing to this summary may blackhole traffic for those unused addresses if they exist elsewhere.",
            title="[bold yellow]Discontiguous Space Detected[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED,
        ))
        
    # Render binary alignment
    try:
        info = calculate_subnet_info(result.supernet.split('/')[0], result.supernet.split('/')[1])
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

        bin_net = format_binary(info.binary_representation.get("network", ""), info.prefix_length, version)
        
        binary_layout = Table(box=box.SIMPLE, show_header=False)
        binary_layout.add_column("Type", style="bold yellow", justify="right")
        binary_layout.add_column("Binary Alignment", justify="left")
        
        binary_layout.add_row("Supernet Bits", bin_net)
        
        from rich.console import Group
        console.print(Panel(
            Group(
                Align.center(binary_layout),
                Align.center(""),
                Align.center("[bold cyan]■ Common Prefix Bits[/bold cyan]    [bold magenta]■ Slack / Host Bits[/bold magenta]")
            ),
            title="[bold yellow]🔢 Supernet Binary Alignment [/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED,
        ))
    except Exception:
        pass

@app.command(name="export-dns", help="Export a subnet to DNS zone files or PTR records.")
def export_dns(
    network: str = typer.Argument(..., help="The subnet to export (e.g., 10.0.0.0/24)."),
    format: str = typer.Option("bind", "--format", help="Output format: bind, csv, json."),
    domain: str = typer.Option("internal.local", "--domain", help="Base domain name for the reverse zone."),
    out: str = typer.Option(None, "--out", help="File to write the output to.")
):
    try:
        from netpulse.subnet.services.dns import export_to_bind, export_to_csv, export_to_json
        
        format = format.lower()
        if format == "bind":
            result = export_to_bind(network, domain)
        elif format == "csv":
            result = export_to_csv(network, domain)
        elif format == "json":
            result = export_to_json(network, domain)
        else:
            console.print(f"[bold red]Error:[/] Unknown format '{format}'. Use bind, csv, or json.")
            raise typer.Exit(1)
            
        if out:
            with open(out, "w") as f:
                f.write(result)
            console.print(f"[bold green]✔ Successfully wrote DNS export to {out}[/bold green]")
        else:
            console.print(result)
            
    except Exception as e:
        console.print(f"[bold red]Error exporting DNS:[/] {e}")
        raise typer.Exit(1)

@ipam_app.command("init")
def ipam_init():
    """Initializes the local IPAM SQLite database."""
    init_db()
    console.print("[bold green]✔ IPAM Database initialized successfully at .netpulse-ipam.db[/bold green]")

@ipam_app.command("list")
def ipam_list():
    """Lists all IP allocations currently tracked in the database."""
    try:
        rows = get_reservations()
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        raise typer.Exit(1)
        
    if not rows:
        console.print("[yellow]No reservations found in IPAM database.[/yellow]")
        return
        
    table = Table(title="[bold cyan]IPAM Reservations[/bold cyan]", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Network", style="bold green")
    table.add_column("Description", style="white")
    table.add_column("Parent", style="cyan")
    
    for row in rows:
        table.add_row(str(row["id"]), row["network"], row["description"], row["parent"])
        
    console.print(table)

@ipam_app.command("free")
def ipam_free(
    parent: str = typer.Argument(..., help="The parent network to check for free space."),
):
    """Calculates and displays the unallocated free space in a tracked parent network."""
    try:
        reserved = get_reservations_for_parent(parent)
    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        raise typer.Exit(1)
        
    try:
        import ipaddress
        parent_net = ipaddress.ip_network(parent, strict=False)
        free_pool = [parent_net]
        
        for r in reserved:
            try:
                r_net = ipaddress.ip_network(r, strict=False)
                new_pool = []
                for free_block in free_pool:
                    if r_net.subnet_of(free_block):
                        new_pool.extend(list(free_block.address_exclude(r_net)))
                    elif not free_block.overlaps(r_net):
                        new_pool.append(free_block)
                free_pool = new_pool
            except ValueError:
                continue
                
        free_pool.sort(key=lambda x: x.network_address)
    except Exception as e:
        console.print(f"[bold red]Error computing free space:[/] {e}")
        raise typer.Exit(1)
        
    table = Table(title=f"[bold green]Free Space in {parent}[/bold green]", box=box.ROUNDED)
    table.add_column("Available Blocks", style="bold green")
    
    for block in free_pool:
        table.add_row(str(block))
        
    console.print(table)

if __name__ == "__main__":
    app()
