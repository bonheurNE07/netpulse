import asyncio
from typing import List, Optional

import typer
from rich.console import Console

from netpulse.discovery.services.discovery import DiscoveryService
from netpulse.discovery.models.discovery import DiscoveryMethod

app = typer.Typer(name="discovery", help="Standalone network discovery and drift engine.")
console = Console()

@app.command()
def scan(
    target: str = typer.Argument(..., help="Target CIDR network"),
    timeout: int = typer.Option(1000, "--timeout", "-t"),
):
    """Stateless network scan returning raw output."""
    with console.status(f"Scanning {target}..."):
        service = DiscoveryService()
        result = asyncio.run(service.discover_network(target, [DiscoveryMethod.ARP], timeout_ms=timeout))
    
    console.print(result.model_dump_json(indent=2))

if __name__ == "__main__":
    app()
