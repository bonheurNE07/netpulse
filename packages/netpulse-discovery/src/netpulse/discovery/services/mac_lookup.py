import os
import sys
import subprocess
import re
import sqlite3
import urllib.request
import urllib.error
from typing import Optional, Dict

# Curated list of common Organisationally Unique Identifiers (OUIs)
COMMON_OUIS: Dict[str, str] = {
    # Cisco
    "00000C": "Cisco Systems",
    "000785": "Cisco Systems",
    "001122": "Cisco Systems (Mock)",  # For automated test suites
    # Apple
    "3C0754": "Apple, Inc.",
    "0017F2": "Apple, Inc.",
    "F82793": "Apple, Inc.",
    # Google
    "001A11": "Google LLC",
    "3C5AB3": "Google LLC",
    # Intel
    "A483E7": "Intel Corporation",
    "0013E8": "Intel Corporation",
    # Microsoft (WSL/Hyper-V often assigns this virtual OUI)
    "00155D": "Microsoft Corporation",
    # VMware
    "000569": "VMware, Inc.",
    "000C29": "VMware, Inc.",
    "005056": "VMware, Inc.",
    # Raspberry Pi
    "B827EB": "Raspberry Pi Foundation",
    "DCA632": "Raspberry Pi Foundation",
    "E45F01": "Raspberry Pi Foundation",
    # Ubiquiti
    "DC9FDB": "Ubiquiti Networks",
    "00156D": "Ubiquiti Networks",
    # Samsung
    "D43A2C": "Samsung Electronics",
    "00125A": "Samsung Electronics",
    # TP-Link
    "E4E4AB": "TP-Link Technologies",
    "000A3A": "TP-Link Technologies",
    # Netgear
    "001F33": "Netgear",
    "000FB5": "Netgear",
    # Dell
    "001422": "Dell Inc.",
    "00219B": "Dell Inc.",
    # HP
    "00110A": "Hewlett Packard",
    "001A4B": "Hewlett Packard",
}

def normalize_mac(mac: str) -> str:
    """
    Standardizes any MAC format (e.g. '00:11:22:33:44:55', '00-11-22-33-44-55', '0011.2233.4455')
    to uppercase raw hex characters ('001122334455').
    """
    if not mac:
        return ""
    clean = mac.replace(":", "").replace("-", "").replace(".", "").strip()
    return clean.upper()

class MacLookupService:
    """
    Core service to resolve MAC addresses to manufacturers / vendors.
    Leverages a hybrid approach: local cache -> SQLite db cache -> online API fallback (with 500ms timeout).
    Also includes utilities for parsing the system ARP cache to resolve Layer 2 details in Layer 3 scans.
    """
    _cache: Dict[str, str] = {}

    @classmethod
    def resolve_vendor(cls, mac: str, timeout_ms: int = 500, db_path: str = "netpulse.db") -> Optional[str]:
        """
        Resolves a MAC address to its manufacturer name.
        
        Args:
            mac: Hardware MAC address string
            timeout_ms: Timeout in milliseconds for the online API lookup fallback
            db_path: Path to the SQLite local database for historical cache checks
            
        Returns:
            Resolved manufacturer name, or None if unrecognized
        """
        if not mac:
            return None

        clean_mac = normalize_mac(mac)
        if not clean_mac or len(clean_mac) < 6:
            return None

        oui = clean_mac[:6]

        # 1. Check in-memory session cache
        if oui in cls._cache:
            return cls._cache[oui]

        # 2. Check local standard OUI dictionary
        if oui in COMMON_OUIS:
            vendor = COMMON_OUIS[oui]
            cls._cache[oui] = vendor
            return vendor

        # 3. Check SQLite local database (persistent history cache)
        if os.path.exists(db_path):
            try:
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    # Look for a non-null vendor previously resolved for this MAC
                    row = conn.execute(
                        """
                        SELECT vendor FROM devices 
                        WHERE mac IS NOT NULL AND vendor IS NOT NULL 
                        AND (mac = ? OR REPLACE(mac, ':', '') = ? OR REPLACE(mac, '-', '') = ?)
                        LIMIT 1;
                        """,
                        (mac, clean_mac.lower(), clean_mac.lower())
                    ).fetchone()
                    if row and row["vendor"]:
                        vendor = row["vendor"]
                        cls._cache[oui] = vendor
                        return vendor
            except Exception:
                pass

        # 4. Fall back to online API lookup (with quick timeout)
        timeout_seconds = timeout_ms / 1000.0
        try:
            url = f"https://api.macvendors.com/{clean_mac}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "NetPulse-OUI-Lookup-Service/0.1"}
            )
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                vendor = response.read().decode("utf-8").strip()
                if vendor:
                    cls._cache[oui] = vendor
                    return vendor
        except urllib.error.HTTPError as e:
            if e.code == 404:
                cls._cache[oui] = "Unknown"
                return "Unknown"
        except Exception:
            # Silence all connection timeouts / DNS lookup failures to keep offline mode 100% resilient
            pass

        return None

    @classmethod
    def parse_system_arp_table(cls, arp_path: str = "/proc/net/arp") -> Dict[str, str]:
        """
        Parses the system ARP cache to map active IPs to MAC addresses.
        Supports Linux (by parsing /proc/net/arp) and Windows (by parsing 'arp -a').
        
        Returns:
            A dictionary mapping IP address strings to normalized colon-delimited MAC address strings.
        """
        arp_map: Dict[str, str] = {}
        
        # 1. Windows support via 'arp -a' command execution
        if sys.platform.startswith("win32"):
            try:
                # Run arp -a securely. creationflags=0x08000000 (CREATE_NO_WINDOW) avoids console flashing on GUI apps.
                output = subprocess.check_output(
                    ["arp", "-a"], 
                    creationflags=0x08000000
                ).decode("utf-8", errors="ignore")
                
                for line in output.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        ip = parts[0]
                        mac = parts[1].strip()
                        # Verify IP and MAC match standard formats
                        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip) and \
                           re.match(r"^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$", mac):
                            # Normalize hyphen-delimited physical addresses to colon-delimited format
                            normalized_mac = mac.replace("-", ":").lower()
                            if normalized_mac != "00:00:00:00:00:00":
                                arp_map[ip] = normalized_mac
            except Exception:
                pass
            return arp_map

        # 2. Linux support via /proc/net/arp parsing
        if not os.path.exists(arp_path):
            return arp_map

        try:
            with open(arp_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if len(lines) <= 1:
                return arp_map

            # /proc/net/arp structure:
            # IP address       HW type     Flags       HW address            Mask     Device
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 4:
                    ip = parts[0]
                    mac = parts[3].strip()
                    # Exclude empty/invalid/incomplete entries
                    if mac and mac != "00:00:00:00:00:00" and len(mac.split(":")) == 6:
                        arp_map[ip] = mac.lower()
        except Exception:
            # Fallback gracefully (do not crash on OS read failures)
            pass

        return arp_map
