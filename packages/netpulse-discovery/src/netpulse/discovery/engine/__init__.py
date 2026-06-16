import logging
import os
from typing import List, Dict, Any, Optional

# Support forced mock mode via environment variable
_force_mock = os.environ.get("NETPULSE_MOCK") == "1"

# This will be imported from the compiled Rust extension
try:
    if _force_mock:
        _engine = None
        logging.info("NetPulse engine running in FORCED MOCK mode via environment variable.")
    else:
        from netpulse.discovery import _engine
except ImportError:
    # Fallback for development/testing without compiled binary
    _engine = None
    logging.warning("_engine module not found. Engine is running in mock mode.")

def scan_arp(target: str, timeout_ms: int = 1000, interface: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Exposes the Rust ARP scanning capability to the Core layer.
    """
    if _engine:
        return _engine.scan_arp(target, timeout_ms, interface)
    
    # Mock fallback for environment without Rust compiled or forced mock mode
    return [
        {"ip": "172.19.57.1", "mac": "00:50:56:C0:00:01", "rtt_ms": 0.35, "status": "up"},
        {"ip": "172.19.57.10", "mac": "00:0C:29:A4:B5:C6", "rtt_ms": 1.24, "status": "up"},
        {"ip": "172.19.57.119", "mac": "00:0C:29:8F:D2:E4", "rtt_ms": 0.08, "status": "up"},
        {"ip": "172.19.57.150", "mac": "00:50:56:E8:A1:B2", "rtt_ms": 4.52, "status": "up"},
    ]

def scan_icmp(target: str, timeout_ms: int = 1000, concurrency: int = 100) -> List[Dict[str, Any]]:
    """
    Exposes the Rust ICMP scanning capability to the Core layer.
    """
    if _engine:
        return _engine.scan_icmp(target, timeout_ms, concurrency)
    
    # Mock fallback for environment without Rust compiled or forced mock mode
    return [
        {"ip": "172.19.57.1", "mac": None, "rtt_ms": 0.42, "status": "up"},
        {"ip": "172.19.57.10", "mac": None, "rtt_ms": 1.58, "status": "up"},
        {"ip": "172.19.57.119", "mac": None, "rtt_ms": 0.12, "status": "up"},
        {"ip": "172.19.57.150", "mac": None, "rtt_ms": 5.11, "status": "up"},
    ]

def traceroute(target: str, max_hops: int = 30, timeout_ms: int = 2000) -> List[Dict[str, Any]]:
    """
    Exposes the Rust traceroute capability to the Core layer.
    """
    if _engine:
        return _engine.traceroute(target, max_hops, timeout_ms)
    
    return [
        {"hop": 1, "ip": "192.168.1.1", "rtt_ms": 1.5},
        {"hop": 2, "ip": target, "rtt_ms": 12.4}
    ]

def sniff_topology(interface: str, duration_ms: int = 5000) -> List[Dict[str, Any]]:
    """
    Exposes the Rust topology sniffing capability to the Core layer.
    """
    if _engine:
        return _engine.sniff_topology(interface, duration_ms)
        
    return [
        {"protocol": "CDP", "source_mac": "00:11:22:33:44:55"}
    ]

__all__ = ["scan_arp", "scan_icmp", "traceroute", "sniff_topology"]
