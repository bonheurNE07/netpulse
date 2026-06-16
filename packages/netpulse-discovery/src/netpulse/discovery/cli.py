import asyncio
from typing import List, Optional
import json
import yaml
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

if __name__ == "__main__":
    app()
