import asyncio
from typing import List, Optional
import json
import yaml
import urllib.request
import time
from pathlib import Path

import typer
from rich.console import Console

from netpulse.discovery.services.discovery import DiscoveryService
from netpulse.discovery.models.discovery import DiscoveryMethod, DiscoveryResult
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
        out_path = Path(output)
        data = result.model_dump(mode="json")
        
        if out_path.suffix == ".json":
            out_path.write_text(json.dumps(data, indent=2))
        elif out_path.suffix in [".yml", ".yaml"]:
            out_path.write_text(yaml.dump(data, sort_keys=False))
        elif out_path.suffix == ".txt":
            lines = [f"Network Scan for {target}", "-"*30]
            for device in data.get("devices", []):
                lines.append(f"IP: {device.get('ip')} | MAC: {device.get('mac')} | Vendor: {device.get('vendor')} | RTT: {device.get('rtt_ms'):.2f}ms")
            out_path.write_text("\n".join(lines))
        else:
            console.print("[red]Unsupported file extension. Use .json, .yaml, or .txt[/red]")
            raise typer.Exit(1)
            
        console.print(f"[green]Successfully exported results to {output}[/green]")
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
    import uvicorn
    from fastapi import FastAPI
    from netpulse.discovery.api import discovery_router
    
    api_app = FastAPI(title="NetPulse Discovery API")
    api_app.include_router(discovery_router)
    
    console.print(f"[green]Starting Discovery API server on http://{host}:{port}[/green]")
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

if __name__ == "__main__":
    app()
