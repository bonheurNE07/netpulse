import asyncio
import ipaddress
import logging
from datetime import datetime, timezone
from typing import List, Optional

from netpulse_core.models.device import Device, DeviceStatus
from netpulse_core.models.discovery import DiscoveryResult, DiscoveryMethod
from netpulse_engine import scan_arp, scan_icmp

logger = logging.getLogger(__name__)

class DiscoveryService:
    """
    Orchestrates network discovery operations.
    Validates inputs, executes via the Engine layer, and aggregates results into Core models.
    """

    async def discover_network(
        self, 
        target_network: str, 
        methods: Optional[List[DiscoveryMethod]] = None,
        timeout_ms: int = 1000,
        interface: Optional[str] = None
    ) -> DiscoveryResult:
        """
        Executes a network discovery scan across the target network.
        
        Args:
            target_network: CIDR notation of the network to scan (e.g., '192.168.1.0/24')
            methods: List of discovery methods to use. Defaults to [DiscoveryMethod.ARP]
            timeout_ms: Timeout in milliseconds for the scan
            interface: Network interface to scan on
            
        Returns:
            DiscoveryResult containing the scan metadata and discovered devices
        """
        if not methods:
            methods = [DiscoveryMethod.ARP]

        # 1. Validate Input
        try:
            network = ipaddress.ip_network(target_network, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid network CIDR '{target_network}': {e}")
            
        # 2. Initialize Result Data
        started_at = datetime.now(timezone.utc)
        errors = []
        raw_devices = []
        
        # 3. Execute Engine (Async offload)
        for method in methods:
            try:
                if method == DiscoveryMethod.ARP:
                    # Offload blocking Rust call to a thread to keep the event loop free
                    results = await asyncio.to_thread(scan_arp, str(network), timeout_ms, interface)
                    raw_devices.extend(results)
                elif method == DiscoveryMethod.ICMP:
                    results = await asyncio.to_thread(scan_icmp, str(network), timeout_ms)
                    raw_devices.extend(results)
                else:
                    errors.append(f"Unsupported discovery method: {method.value}")
            except Exception as e:
                logger.error(f"Error during {method.value} scan: {e}")
                errors.append(f"{method.value} scan failed: {str(e)}")

        # 4. Process Data into Models
        devices: List[Device] = []
        seen_ips = set()
        
        for raw_device in raw_devices:
            ip = raw_device.get("ip")
            if not ip or ip in seen_ips:
                continue
                
            try:
                # Let Pydantic validate and construct the model
                device = Device(
                    ip=ip,
                    mac=raw_device.get("mac"),
                    rtt_ms=raw_device.get("rtt_ms"),
                    status=raw_device.get("status", DeviceStatus.UNKNOWN)
                )
                devices.append(device)
                seen_ips.add(ip)
            except Exception as e:
                logger.warning(f"Failed to parse device data {raw_device}: {e}")
                errors.append(f"Failed to parse device {ip}: {str(e)}")
                
        finished_at = datetime.now(timezone.utc)
        
        # Determine overall status
        if len(errors) > 0 and len(devices) == 0:
            status = "failed"
        elif len(errors) > 0:
            status = "partial"
        else:
            status = "completed"

        # 5. Aggregate & Return
        result = DiscoveryResult(
            network=str(network),
            methods=methods,
            status=status,
            errors=errors,
            devices=devices,
            started_at=started_at,
            finished_at=finished_at,
            stats={
                "scanned": network.num_addresses,
                "responsive": len(devices)
            }
        )
        
        return result
