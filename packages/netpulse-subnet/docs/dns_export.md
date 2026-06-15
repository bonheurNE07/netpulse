# Automated DNS PTR / Zone File Generation

Netpulse Subnet includes a native **DNS Export Engine** designed to instantly translate your subnet calculations into ready-to-deploy DNS configuration files. 

When you allocate large blocks of IPs, generating `in-addr.arpa` or IPv6 `ip6.arpa` reverse lookup zones manually can be tedious and error-prone. The `export-dns` command handles this automatically.

## BIND Zone Generation (`--format bind`)

By default, the tool outputs a BIND-compatible reverse zone template.

### IPv4 Example
```bash
netpulse-subnet export-dns 10.0.0.0/24 --format bind --domain internal.corp
```

For standard octet-boundary IPv4 networks (like `/24`), the engine will intelligently utilize BIND's `$GENERATE` directive to create a compact, highly optimized file:

```bind
$ORIGIN 0.0.10.in-addr.arpa.
$TTL 86400
@   IN  SOA ns1.internal.corp. admin.internal.corp. (
            2026061501 ; Serial
            3600       ; Refresh
            1800       ; Retry
            604800     ; Expire
            86400 )    ; Minimum TTL
    IN  NS  ns1.internal.corp.
    IN  NS  ns2.internal.corp.

$GENERATE 1-254 $ IN PTR host-10-0-0-$.internal.corp.
```

### IPv6 Example
IPv6 reverse DNS requires expanding the prefix into a highly verbose "nibble" format. The tool does this automatically:

```bash
netpulse-subnet export-dns 2001:db8::/32 --format bind --domain ipv6.local
```
This correctly calculates the origin as `$ORIGIN 8.b.d.0.1.0.0.2.ip6.arpa.` and builds out the PTR records.

## Exporting to Files (`--out`)
To write the generation directly to a `.zone` file instead of printing to the terminal, use the `--out` argument:

```bash
netpulse-subnet export-dns 192.168.1.0/24 --out 192.168.1.0.zone
```

## Integrating with Infoblox / Windows DNS (`--format csv` | `--format json`)

If you are importing records into IPAM solutions like Infoblox or a proprietary database, you can export structured data instead of BIND files.

### CSV Export
```bash
netpulse-subnet export-dns 10.0.0.0/30 --format csv
```
**Output:**
```csv
IP Address,Record Type,Target
10.0.0.1,PTR,host-10-0-0-1.internal.local.
10.0.0.2,PTR,host-10-0-0-2.internal.local.
```

### JSON Export
```bash
netpulse-subnet export-dns 10.0.0.0/30 --format json
```
**Output:**
```json
[
  {
    "ip": "10.0.0.1",
    "ptr": "host-10-0-0-1.internal.local."
  },
  {
    "ip": "10.0.0.2",
    "ptr": "host-10-0-0-2.internal.local."
  }
]
```

## Python Integration
For developers building backend systems, you can import the generators directly:

```python
from netpulse.subnet.services.dns import export_to_bind, export_to_json

bind_text = export_to_bind("192.168.0.0/24", domain="datacenter.local")
json_data = export_to_json("192.168.0.0/24", domain="datacenter.local")
```
