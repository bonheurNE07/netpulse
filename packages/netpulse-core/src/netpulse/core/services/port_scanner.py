import asyncio
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Standard well-known ports and services mapping
COMMON_PORTS_MAP: Dict[int, str] = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    135: "MSRPC",
    139: "NetBIOS",
    143: "IMAP",
    443: "HTTPS",
    445: "Microsoft-DS",
    993: "IMAPS",
    995: "POP3S",
    1433: "MSSQL",
    1521: "Oracle",
    3306: "MySQL",
    3389: "RDP",
    5432: "PostgreSQL",
    5900: "VNC",
    8080: "HTTP-Proxy",
    8443: "HTTPS-Alt"
}

class PortScannerService:
    """
    High-performance, non-blocking asynchronous TCP Connect port scanner.
    Queries target ports concurrently to identify active network services.
    """

    def __init__(self, max_concurrency: int = 200):
        # Prevent running out of system file descriptors
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def scan_single_port(self, ip: str, port: int, timeout_s: float) -> Optional[Dict[str, Any]]:
        """
        Attempts to establish a TCP connection to a specific port on an IP address.
        """
        async with self.semaphore:
            try:
                # Attempt to open connection
                conn = asyncio.open_connection(ip, port)
                reader, writer = await asyncio.wait_for(conn, timeout=timeout_s)
                
                # Connection successful! Clean up socket properly
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                
                service = COMMON_PORTS_MAP.get(port, "unknown")
                return {
                    "port": port,
                    "service": service,
                    "status": "open"
                }
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                # Port is closed or filtered
                return None
            except Exception as e:
                logger.debug(f"Unhandled exception scanning port {port} on {ip}: {e}")
                return None

    async def scan_device_ports(
        self, 
        ip: str, 
        ports: List[int], 
        timeout_ms: int = 300
    ) -> List[Dict[str, Any]]:
        """
        Scans a list of target ports on a single device concurrently.
        """
        timeout_s = timeout_ms / 1000.0
        tasks = [self.scan_single_port(ip, port, timeout_s) for port in ports]
        results = await asyncio.gather(*tasks)
        
        # Filter out unsuccessful connections (None values)
        return [r for r in results if r is not None]

    async def scan_multiple_devices_ports(
        self,
        ips: List[str],
        ports: List[int],
        timeout_ms: int = 300
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scans a list of target ports across multiple devices concurrently.
        Returns a mapping of IP address string to their discovered open ports.
        """
        tasks = {}
        for ip in ips:
            tasks[ip] = self.scan_device_ports(ip, ports, timeout_ms)
            
        results = await asyncio.gather(*tasks.values())
        
        return {ip: result for ip, result in zip(tasks.keys(), results)}
