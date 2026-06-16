import strawberry
from typing import List, Optional
import json

from netpulse.discovery.services.discovery import DiscoveryService
from netpulse.discovery.models.discovery import DiscoveryMethod

@strawberry.type
class DeviceType:
    id: str
    ip: str
    mac: Optional[str]
    vendor: Optional[str]
    os_guess: Optional[str]
    rtt_ms: Optional[float]
    status: str
    
    @strawberry.field
    def services(self) -> str:
        # We return a JSON string to represent dynamic port mapping in GraphQL
        # In a more robust implementation, this could be a list of Service types
        return "{}"

@strawberry.type
class DiscoveryResultType:
    network: str
    status: str
    devices: List[DeviceType]

@strawberry.type
class Query:
    @strawberry.field
    async def scan_network(self, target: str, timeout_ms: int = 1000) -> DiscoveryResultType:
        """Run a network discovery scan via GraphQL."""
        service = DiscoveryService()
        result = await service.discover_network(target, [DiscoveryMethod.ARP], timeout_ms)
        
        device_types = []
        for d in result.devices:
            # Reconstruct services dict
            services_json = json.dumps(d.services) if hasattr(d, 'services') and d.services else "{}"
            
            dt = DeviceType(
                id=str(d.id),
                ip=str(d.ip),
                mac=d.mac,
                vendor=d.vendor,
                os_guess=d.os_guess,
                rtt_ms=d.rtt_ms,
                status=d.status.value
            )
            # Override the field method slightly for simplicity in this MVP
            dt.services = lambda s_json=services_json: s_json
            device_types.append(dt)
            
        return DiscoveryResultType(
            network=result.network,
            status=result.status,
            devices=device_types
        )

schema = strawberry.Schema(query=Query)
