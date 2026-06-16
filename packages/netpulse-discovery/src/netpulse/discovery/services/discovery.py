import asyncio
import ipaddress
import logging
from datetime import datetime, timezone
from typing import List, Optional, Callable

from netpulse.discovery.models.device import Device, DeviceStatus
from netpulse.discovery.models.discovery import DiscoveryResult, DiscoveryMethod
from netpulse.discovery.engine import scan_arp, scan_icmp

from netpulse.discovery.services.mac_lookup import MacLookupService
from netpulse.discovery.services.port_scanner import PortScannerService

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
        interface: Optional[str] = None,
        ports: Optional[List[int]] = None,
        plugins: Optional[List[Callable]] = None
    ) -> DiscoveryResult:
        """
        Executes a network discovery scan across the target network.
        
        Args:
            target_network: CIDR notation of the network to scan (e.g., '192.168.1.0/24')
            methods: List of discovery methods to use. Defaults to [DiscoveryMethod.ARP]
            timeout_ms: Timeout in milliseconds for the scan
            interface: Network interface to scan on
            ports: Optional list of TCP ports to scan on active hosts
            plugins: Optional list of callback functions to process each device
            
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

        # Fetch local system ARP cache for ICMP sweeps
        arp_cache = {}
        if any(m == DiscoveryMethod.ICMP for m in methods):
            arp_cache = MacLookupService.parse_system_arp_table()

        # 4. Process Data into Models
        devices: List[Device] = []
        seen_ips = set()
        
        for raw_device in raw_devices:
            ip = raw_device.get("ip")
            if not ip or ip in seen_ips:
                continue
                
            try:
                # 1. Resolve MAC address if missing (e.g. from ICMP scan on local subnet)
                mac = raw_device.get("mac")
                if not mac and ip in arp_cache:
                    mac = arp_cache[ip]

                # 2. Resolve vendor if MAC is present
                vendor = None
                if mac:
                    vendor = MacLookupService.resolve_vendor(mac)

                # Let Pydantic validate and construct the model
                os_guess = None
                ttl = raw_device.get("ttl")
                if ttl:
                    if ttl <= 64:
                        os_guess = "Linux/macOS"
                    elif ttl <= 128:
                        os_guess = "Windows"
                    else:
                        os_guess = "Network/Router"

                device = Device(
                    ip=ip,
                    mac=mac,
                    vendor=vendor,
                    os_guess=os_guess,
                    rtt_ms=raw_device.get("rtt_ms"),
                    status=raw_device.get("status", DeviceStatus.UNKNOWN)
                )

                # Execute plugins synchronously
                if plugins:
                    for plugin in plugins:
                        try:
                            plugin(device)
                        except Exception as e:
                            logger.error(f"Plugin execution failed for {ip}: {e}")

                devices.append(device)
                seen_ips.add(ip)
            except Exception as e:
                logger.warning(f"Failed to parse device data {raw_device}: {e}")
                errors.append(f"Failed to parse device {ip}: {str(e)}")
                
        # 4.5 Execute Asynchronous TCP Port Scan on Discovered 'UP' Hosts
        if ports and devices:
            active_devices = [d for d in devices if d.status == DeviceStatus.UP]
            if active_devices:
                active_ips = [str(d.ip) for d in active_devices]
                try:
                    scanner = PortScannerService()
                    # Keep the port timeout snappy (max 500ms) to ensure NetPulse remains extremely fast
                    port_scan_timeout = min(timeout_ms, 500)
                    scan_results = await scanner.scan_multiple_devices_ports(
                        ips=active_ips,
                        ports=ports,
                        timeout_ms=port_scan_timeout
                    )
                    
                    # Map discovered open ports back to device metadata
                    for device in active_devices:
                        ip_str = str(device.ip)
                        if ip_str in scan_results:
                            device.metadata["open_ports"] = scan_results[ip_str]
                            services = {}
                            for port_info in scan_results[ip_str]:
                                port = port_info["port"]
                                svc = port_info["service"]
                                banner = port_info.get("banner")
                                services[port] = f"{svc} - {banner}" if banner else svc
                            device.services = services
                except Exception as pe:
                    logger.error(f"Error during port scanning execution: {pe}")
                    errors.append(f"Port scan failed: {str(pe)}")

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
