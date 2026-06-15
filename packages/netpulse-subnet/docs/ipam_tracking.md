# Stateful IPAM Database Tracking

Netpulse Subnet now natively supports a lightweight **Stateful IP Address Management (IPAM)** system powered by SQLite. This capability solves the problem of subnet exhaustion and accidental allocation overlap without requiring a heavy, external IPAM appliance like Netbox or Infoblox.

## Overview

When network engineers calculate subnets via the `split` or `vlsm` commands, the tool typically performs "stateless" math. If you run a VLSM calculation twice on the same `192.168.1.0/24` network, you'll receive the exact same allocation blocks both times.

By initializing the local IPAM state database and appending `--commit` to your commands, you instruct the engine to **persist** the results. Future calculations automatically read from this state file and intelligently "punch out" reserved blocks using `address_exclude()`.

## Initializing State

Just like Terraform or Git, the local database is bound to your project's Current Working Directory (CWD).

```bash
netpulse-subnet ipam init
```

*This generates a hidden `.netpulse-ipam.db` SQLite file.*

### Changing the DB Location
If you are running automated scripts across multiple environments, you can override the target database path using an environment variable:
```bash
export NETPULSE_IPAM_DB="/var/lib/netpulse/prod-ipam.db"
netpulse-subnet ipam init
```

## Reserving Subnets

To commit a new subnetting calculation to state, run `split` or `vlsm` with the `--commit` flag. 

### VLSM Example
```bash
netpulse-subnet vlsm 10.0.0.0/24 --req "HR=100,Dev=50" --commit
```
**Output Highlights:**
1. Calculates that `HR` needs a `/25` (`10.0.0.0/25`).
2. Calculates that `Dev` needs a `/26` (`10.0.0.128/26`).
3. Saves both records into the SQLite database with their names.

If you run another requirement immediately after:
```bash
netpulse-subnet vlsm 10.0.0.0/24 --req "Sales=20" --commit
```
The allocation engine queries the IPAM database, detects that `10.0.0.0/25` and `10.0.0.128/26` are taken, and automatically allocates the next available valid block: `10.0.0.192/27`.

## Auditing and Free Space

### Listing Reservations
```bash
netpulse-subnet ipam list
```
Returns a beautiful terminal table showing the internal ID, reserved CIDR block, the text description (e.g., the requirement name), and the original Parent network it was split from.

### Calculating Free Space
You can proactively query a parent network to see exactly what address space remains unallocated.
```bash
netpulse-subnet ipam free 10.0.0.0/24
```
**Example Output:**
```text
╭──────────────────╮
│ Available Blocks │
├──────────────────┤
│ 10.0.0.224/27    │
╰──────────────────╯
```

## Python Integration
For backend developers building network automation REST APIs, the `services/ipam.py` package exports easy-to-use hooks:

```python
from netpulse.subnet.services.ipam import get_reservations_for_parent
from netpulse.subnet.services.subnet import allocate_vlsm

# 1. Fetch current taken space
reserved = get_reservations_for_parent("192.168.1.0/24")

# 2. Safely calculate next block
result = allocate_vlsm("192.168.1.0/24", requirements=[...], reserved_blocks=reserved)
```
