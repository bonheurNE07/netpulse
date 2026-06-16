import asyncio
from typing import List, Optional, Dict, Any
import json
import yaml
import urllib.request
import time
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from prometheus_client import make_asgi_app
from strawberry.fastapi import GraphQLRouter
from netpulse.discovery.graphql import schema

import typer
from rich.console import Console

from netpulse.discovery.services.discovery import DiscoveryService
from netpulse.discovery.models.discovery import DiscoveryMethod, DiscoveryResult
from netpulse.discovery.engine import traceroute as engine_traceroute, sniff_topology
from netpulse.discovery.services.drift import DriftService

app = typer.Typer(name="discovery", help="Standalone network discovery and drift engine.")
console = Console()

@app.command(name="scan")
def scan(
    target: str = typer.Argument(..., help="Target CIDR network"),
    timeout: int = typer.Option(1000, "--timeout", "-t"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export results to a file (.json, .yaml, .txt)"),
):
    """Stateless network scan returning raw output."""
    with console.status(f"Scanning {target}..."):
        service = DiscoveryService()
        result = asyncio.run(service.discover_network(target, [DiscoveryMethod.ARP], timeout_ms=timeout))
    
    # Export if requested
    if output:
        data = result.model_dump(mode="json")
        export_results(data, output, "Scan")
    else:
        # Just print to console
        console.print(result.model_dump_json(indent=2))

@app.command(name="drift")
def drift(
    baseline_file: str = typer.Argument(..., help="Path to baseline scan JSON file"),
    new_file: str = typer.Argument(..., help="Path to new scan JSON file"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Export drift results to a file (.json, .yaml, .txt)"),
):
    """Compute exact network drift between two scan files."""
    try:
        baseline_path = Path(baseline_file)
        new_path = Path(new_file)
        
        baseline_data = json.loads(baseline_path.read_text())
        new_data = json.loads(new_path.read_text())
        
        baseline_scan = DiscoveryResult(**baseline_data)
        new_scan = DiscoveryResult(**new_data)
        
    except Exception as e:
        console.print(f"[red]Failed to parse input scan files: {e}[/red]")
        raise typer.Exit(1)
        
    with console.status("Computing network drift..."):
        service = DriftService()
        result = service.calculate_drift(new_scan=new_scan, old_scan=baseline_scan)
        
    if output:
        out_path = Path(output)
        data = result.model_dump(mode="json")
        
        if out_path.suffix == ".json":
            out_path.write_text(json.dumps(data, indent=2))
        elif out_path.suffix in [".yml", ".yaml"]:
            out_path.write_text(yaml.dump(data, sort_keys=False))
        elif out_path.suffix == ".txt":
            lines = [f"Drift Analysis for {result.network}", "-"*30]
            lines.append(f"Joined: {len(result.joined)}")
            lines.append(f"Left: {len(result.left)}")
            lines.append(f"Modified: {len(result.modified)}")
            lines.append(f"Unchanged: {len(result.unchanged)}")
            out_path.write_text("\n".join(lines))
        else:
            console.print("[red]Unsupported file extension. Use .json, .yaml, or .txt[/red]")
            raise typer.Exit(1)
            
        console.print(f"[green]Successfully exported drift results to {output}[/green]")
    else:
        console.print(result.model_dump_json(indent=2))

@app.command(name="serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host IP to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
):
    """Start the standalone NetPulse Discovery REST API server."""
    from netpulse.discovery.api import discovery_router
    
    api_app = FastAPI(title="NetPulse Discovery API")
    
    api_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    api_app.include_router(discovery_router)
    
    # Mount Prometheus metrics
    metrics_app = make_asgi_app()
    api_app.mount("/metrics", metrics_app)
    
    # Mount GraphQL
    graphql_app = GraphQLRouter(schema)
    api_app.include_router(graphql_app, prefix="/graphql")
    
    console.print(f"[green]Starting API server on {host}:{port}[/green]")
    uvicorn.run(api_app, host=host, port=port)

@app.command(name="watch")
def watch(
    target: str = typer.Argument(..., help="Target CIDR network"),
    interval: int = typer.Option(300, "--interval", "-i", help="Interval between scans in seconds"),
    webhook: Optional[str] = typer.Option(None, "--webhook", "-w", help="URL to POST drift alerts to"),
    timeout: int = typer.Option(1000, "--timeout", "-t", help="Timeout per host in ms"),
):
    """Run discovery continuously and alert on network drift."""
    console.print(f"[bold blue]Starting NetPulse Daemon Mode for {target}[/bold blue]")
    console.print(f"Interval: {interval}s | Webhook: {'Enabled' if webhook else 'Disabled'}")
    
    service = DiscoveryService()
    drift_service = DriftService()
    previous_scan: Optional[DiscoveryResult] = None
    
    try:
        while True:
            start_time = time.time()
            scan_result = asyncio.run(service.discover_network(target, [DiscoveryMethod.ARP], timeout_ms=timeout))
            
            if previous_scan:
                drift = drift_service.calculate_drift(scan_result, previous_scan)
                has_drift = len(drift.joined) > 0 or len(drift.left) > 0 or len(drift.modified) > 0
                
                if has_drift:
                    msg = f"[bold red]DRIFT DETECTED![/bold red] Joined: {len(drift.joined)}, Left: {len(drift.left)}, Modified: {len(drift.modified)}"
                    console.print(msg)
                    
                    if webhook:
                        try:
                            req = urllib.request.Request(
                                webhook, 
                                data=drift.model_dump_json().encode('utf-8'),
                                headers={'Content-Type': 'application/json'}
                            )
                            urllib.request.urlopen(req, timeout=5)
                            console.print("[green]Webhook successfully triggered[/green]")
                        except Exception as e:
                            console.print(f"[yellow]Failed to trigger webhook: {e}[/yellow]")
                else:
                    console.print(f"[dim]Scan complete. No topological drift detected. ({len(scan_result.devices)} active hosts)[/dim]")
            else:
                console.print(f"[green]Baseline scan complete. {len(scan_result.devices)} hosts discovered. Watching for changes...[/green]")
                
            previous_scan = scan_result
            
            # Sleep until next interval
            elapsed = time.time() - start_time
            sleep_time = max(0.1, interval - elapsed)
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        console.print("[yellow]Shutting down watch daemon...[/yellow]")

@app.command(name="generate-inventory")
def generate_inventory(
    target: str = typer.Argument(..., help="Target CIDR network"),
    output: str = typer.Option("hosts.yaml", "--output", "-o", help="Output inventory file path"),
    format: str = typer.Option("ansible", "--format", "-f", help="Format: 'ansible'"),
    timeout: int = typer.Option(1000, "--timeout", "-t"),
):
    """Generate an Infrastructure-as-Code inventory (e.g. Ansible) from a live network scan."""
    with console.status(f"Scanning {target} to generate inventory..."):
        service = DiscoveryService()
        result = asyncio.run(service.discover_network(target, [DiscoveryMethod.ARP], timeout_ms=timeout))
        
    out_path = Path(output)
    
    if format.lower() == "ansible":
        hosts_dict = {}
        for device in result.devices:
            hosts_dict[str(device.ip)] = {
                "mac": device.mac,
                "vendor": device.vendor,
                "rtt_ms": device.rtt_ms
            }
            
        ansible_inv = {
            "all": {
                "hosts": hosts_dict
            }
        }
        
        out_path.write_text(yaml.dump(ansible_inv, sort_keys=False))
        console.print(f"[green]Successfully generated Ansible inventory with {len(result.devices)} hosts at {output}[/green]")
    else:
        console.print(f"[red]Unsupported inventory format: {format}[/red]")
        raise typer.Exit(1)

def generate_mermaid(data: Any, command_name: str) -> str:
    if command_name.lower() == "traceroute":
        lines = ["graph TD", "  start[\"Localhost\"]"]
        prev = "start"
        for idx, hop in enumerate(data):
            curr = f"h{idx}"
            lines.append(f"  {curr}[\"{hop['ip']}\"]")
            rtt = f"{hop.get('rtt_ms'):.2f}ms" if hop.get('rtt_ms') else "*"
            lines.append(f"  {prev} -- \"{rtt}\" --> {curr}")
            prev = curr
        return "\n".join(lines)
    elif command_name.lower() == "scan":
        network = data.get("network", "Network")
        lines = ["graph TD", f"  net[\"{network}\"]"]
        for idx, dev in enumerate(data.get("devices", [])):
            ip = dev.get("ip")
            vendor = dev.get("vendor") or "Unknown"
            lines.append(f"  dev{idx}[\"{ip}\\n({vendor})\"]")
            lines.append(f"  net --> dev{idx}")
        return "\n".join(lines)
    return "graph TD\n  A[Unsupported Command]"

def generate_graphml(data: Any, command_name: str) -> str:
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="d0" for="node" attr.name="label" attr.type="string"/>',
        '  <graph id="G" edgedefault="directed">'
    ]
    if command_name.lower() == "traceroute":
        xml.append('    <node id="Localhost"><data key="d0">Localhost</data></node>')
        prev = "Localhost"
        for hop in data:
            curr = hop["ip"]
            # Avoid duplicate node IDs by using a clean XML node
            xml.append(f'    <node id="{curr}"><data key="d0">{curr}</data></node>')
            xml.append(f'    <edge source="{prev}" target="{curr}"/>')
            prev = curr
    elif command_name.lower() == "scan":
        network = data.get("network", "Network")
        xml.append(f'    <node id="net"><data key="d0">{network}</data></node>')
        for dev in data.get("devices", []):
            ip = dev.get("ip")
            vendor = dev.get("vendor") or "Unknown"
            xml.append(f'    <node id="{ip}"><data key="d0">{ip} ({vendor})</data></node>')
            xml.append(f'    <edge source="net" target="{ip}"/>')
    
    xml.append('  </graph>')
    xml.append('</graphml>')
    return "\n".join(xml)

def export_results(data: Any, output: str, command_name: str):
    """Helper to export CLI command results to json, yaml, txt, mermaid, or graphml."""
    out_path = Path(output)
    
    if out_path.suffix == ".json":
        out_path.write_text(json.dumps(data, indent=2))
    elif out_path.suffix in [".yml", ".yaml"]:
        out_path.write_text(yaml.dump(data, sort_keys=False))
    elif out_path.suffix == ".txt":
        out_path.write_text(f"NetPulse {command_name} Output\n" + "="*40 + "\n")
        out_path.open("a").write(json.dumps(data, indent=2))
    elif out_path.suffix == ".mermaid":
        out_path.write_text(generate_mermaid(data, command_name))
    elif out_path.suffix == ".graphml":
        out_path.write_text(generate_graphml(data, command_name))
    else:
        console.print(f"[yellow]Unknown extension {out_path.suffix}, defaulting to JSON[/yellow]")
        out_path.write_text(json.dumps(data, indent=2))
    console.print(f"[green]Results saved to {output}[/green]")

@app.command(name="traceroute")
def traceroute_cmd(
    target: str = typer.Argument(..., help="Target IP address"),
    max_hops: int = typer.Option(30, "--max-hops", "-m", help="Maximum number of hops to trace"),
    timeout: int = typer.Option(2000, "--timeout", "-t", help="Timeout per hop in milliseconds"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Path to export results (.json, .yaml, .txt)"),
):
    """Perform a high-speed ICMP traceroute to the target."""
    with console.status(f"Tracing route to {target} (max {max_hops} hops)..."):
        try:
            results = engine_traceroute(target, max_hops, timeout)
        except Exception as e:
            console.print(f"[red]Traceroute failed: {e}[/red]")
            raise typer.Exit(1)
            
    console.print(f"\n[bold blue]Traceroute to {target}[/bold blue]")
    for hop in results:
        rtt = f"{hop['rtt_ms']:.2f}ms" if hop['rtt_ms'] is not None else "*"
        console.print(f"{hop['hop']:2d}  {hop['ip']:<15}  {rtt}")
        
    if output:
        export_results(results, output, "Traceroute")

@app.command(name="sniff")
def sniff_cmd(
    interface: str = typer.Argument(..., help="Network interface to sniff on (e.g. eth0)"),
    duration: int = typer.Option(10, "--duration", "-d", help="Duration to sniff in seconds"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Path to export results (.json, .yaml, .txt)"),
):
    """Passively sniff the network interface for CDP and LLDP topology broadcasts."""
    console.print(f"[bold blue]Sniffing on {interface} for {duration} seconds...[/bold blue]")
    try:
        results = sniff_topology(interface, duration * 1000)
    except Exception as e:
        console.print(f"[red]Sniffing failed: {e}[/red]")
        raise typer.Exit(1)
        
    if not results:
        console.print("[yellow]No CDP or LLDP broadcasts detected in the timeframe.[/yellow]")
    else:
        console.print("\n[bold green]Topology Broadcasts Detected:[/bold green]")
        for pkt in results:
            console.print(f"- Protocol: [cyan]{pkt['protocol']}[/cyan] from [magenta]{pkt['source_mac']}[/magenta]")
            
    if output:
        export_results(results, output, "Topology Sniffer")

if __name__ == "__main__":
    app()
