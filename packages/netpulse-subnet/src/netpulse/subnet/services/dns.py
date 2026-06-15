import ipaddress
import json
import csv
import io
from typing import List, Dict

def generate_reverse_zone_name(network: str) -> str:
    """Generates the appropriate reverse DNS zone name (in-addr.arpa or ip6.arpa) for a given network."""
    net = ipaddress.ip_network(network, strict=False)
    
    if net.version == 4:
        # IPv4 reverse zones usually fall on octet boundaries (/8, /16, /24)
        # We can extract the network address octets depending on prefix length
        parts = str(net.network_address).split('.')
        if net.prefixlen >= 24:
            return f"{parts[2]}.{parts[1]}.{parts[0]}.in-addr.arpa"
        elif net.prefixlen >= 16:
            return f"{parts[1]}.{parts[0]}.in-addr.arpa"
        elif net.prefixlen >= 8:
            return f"{parts[0]}.in-addr.arpa"
        else:
            return "in-addr.arpa"
    else:
        # IPv6 reverse zones are nibble-based
        # E.g., 2001:db8::/32 -> 8.b.d.0.1.0.0.2.ip6.arpa
        # 1. Expand the address into 32 hex digits
        expanded = net.network_address.exploded.replace(':', '')
        # 2. Determine how many nibbles to include based on prefixlen (prefixlen / 4)
        nibbles_count = net.prefixlen // 4
        # 3. Take the first `nibbles_count` digits, reverse them, and join with '.'
        nibbles = list(expanded[:nibbles_count])
        nibbles.reverse()
        return ".".join(nibbles) + ".ip6.arpa"

def get_ptr_records(network: str, domain: str) -> List[Dict[str, str]]:
    """Returns a list of dictionaries with IP and generated PTR name."""
    net = ipaddress.ip_network(network, strict=False)
    domain = domain.rstrip('.')
    records = []
    
    # We shouldn't iterate an entire /8 or large IPv6 prefix.
    # We will limit to 65536 max hosts to prevent memory bombs.
    max_hosts = 65536
    count = 0
    
    for ip in net.hosts():
        if count >= max_hosts:
            break
        
        # Simple heuristic for PTR generation: replace '.' or ':' with '-'
        # Example: 192.168.1.10 -> host-192-168-1-10.domain.com
        if net.version == 4:
            safe_ip = str(ip).replace('.', '-')
        else:
            safe_ip = str(ip).replace(':', '')
            
        ptr = f"host-{safe_ip}.{domain}."
        
        records.append({
            "ip": str(ip),
            "ptr": ptr,
            "reverse_name": ip.reverse_pointer
        })
        count += 1
        
    return records

def export_to_bind(network: str, domain: str) -> str:
    """Generates a BIND-compatible reverse zone file template."""
    net = ipaddress.ip_network(network, strict=False)
    zone_name = generate_reverse_zone_name(network)
    
    lines = [
        f"$ORIGIN {zone_name}.",
        f"$TTL 86400",
        f"@   IN  SOA ns1.{domain}. admin.{domain}. (",
        f"            2026061501 ; Serial",
        f"            3600       ; Refresh",
        f"            1800       ; Retry",
        f"            604800     ; Expire",
        f"            86400 )    ; Minimum TTL",
        f"    IN  NS  ns1.{domain}.",
        f"    IN  NS  ns2.{domain}.",
        ""
    ]
    
    # Instead of printing 65k records individually, we can use BIND's $GENERATE for IPv4 /24 if applicable
    if net.version == 4 and net.prefixlen == 24:
        prefix_dash = net.network_address.exploded.replace('.', '-').rsplit('-', 1)[0]
        lines.append(f"$GENERATE 1-254 $ IN PTR host-{prefix_dash}-$.{domain}.")
    else:
        # Standard fallback for smaller or IPv6 blocks
        records = get_ptr_records(network, domain)
        for r in records:
            # We want the host part of the reverse pointer relative to the origin
            # Example: for 10.0.0.5 inside 0.0.10.in-addr.arpa
            # reverse_pointer is 5.0.0.10.in-addr.arpa. 
            # We strip the origin part.
            full_ptr = r["reverse_name"]
            if full_ptr.endswith(zone_name):
                # +1 to remove the dot separator
                relative_ptr = full_ptr[:-(len(zone_name)+1)] 
            else:
                relative_ptr = full_ptr
                
            lines.append(f"{relative_ptr:<30} IN PTR {r['ptr']}")
            
    return "\n".join(lines)

def export_to_csv(network: str, domain: str) -> str:
    """Generates CSV output for DNS records."""
    records = get_ptr_records(network, domain)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["IP Address", "Record Type", "Target"])
    for r in records:
        writer.writerow([r["ip"], "PTR", r["ptr"]])
    return output.getvalue()

def export_to_json(network: str, domain: str) -> str:
    """Generates structured JSON output for DNS records."""
    records = get_ptr_records(network, domain)
    # Return as list of standard dicts
    out_records = [{"ip": r["ip"], "ptr": r["ptr"]} for r in records]
    return json.dumps(out_records, indent=2)
