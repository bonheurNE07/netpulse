# Usage Guide

`netpulse-subnet` provides both a beautiful Terminal User Interface (CLI) and a REST API. 

## CLI Usage

If you installed the package via `pip` or `uv`, the `netpulse-subnet` command is immediately available in your terminal.

### 1. Subnet Info (Calculator)
Retrieve detailed binary alignments, masks, and boundaries for any IP/CIDR. Supports both IPv4 and IPv6 out-of-the-box!
```bash
# IPv4 Example
netpulse-subnet info 192.168.1.50/24

# IPv6 Example
netpulse-subnet info 2001:db8::1/64
```

### 2. Subnet Splitter (FLSM)
Split a massive network block into smaller, equal-sized subnets. *Note: For massive IPv6 blocks, the split is capped at 65,536 subnets to prevent memory exhaustion.*

**By number of subnets:**
```bash
netpulse-subnet split 10.0.0.0/8 --subnets 4
```
**By required hosts per subnet:**
```bash
netpulse-subnet split 10.0.0.0/8 --hosts 2000
```
**IPv6 Splits:**
```bash
netpulse-subnet split 2001:db8::/48 --subnets 10
```

### 3. VLSM Planner
Plan a Variable-Length Subnet network without wasting IPs. Pass requirements as a comma-separated list of `Name=Hosts`.
```bash
netpulse-subnet vlsm 192.168.1.0/24 --req "HR=120,Dev=50,Sales=20,Guest=10"
```

### 4. Discover
Check which subnet out of a provided list an IP belongs to.
```bash
netpulse-subnet discover 192.168.1.45 --subnets "192.168.1.0/26,192.168.1.64/26"
```

### 5. Validate Overlaps
Validate a list of subnets to ensure there are no routing conflicts or overlaps. You can optionally supply a `--parent` block to calculate remaining free space.

**Inline CLI Validation:**
```bash
netpulse-subnet validate 192.168.1.0/24 192.168.1.128/25 --parent 192.168.1.0/23
```

**Validating from a File:**
You can supply a `.txt` file with one CIDR per line.
```bash
netpulse-subnet validate --file legacy_subnets.txt
```

### 6. Summarize Routes (Supernetting)
Summarize a list of networks into the tightest encompassing Supernet CIDR block. The CLI will warn you if the new supernet creates routing "slack" (meaning it covers IPs that were not explicitly provided in the input list).

```bash
netpulse-subnet summarize 192.168.0.0/24 192.168.1.0/24 192.168.2.0/24 192.168.3.0/24
```
**Validating from a File:**
You can supply a `.txt` file with one CIDR per line.
```bash
netpulse-subnet summarize --file routing_table.txt
```

### 7. Stateful IPAM Tracking
Optionally store subnet allocations using the built-in SQLite IPAM database. This prevents you from accidentally allocating the same IP block twice.

**Initialize IPAM Database:**
```bash
netpulse-subnet ipam init
```

**Commit Allocations:**
Add `--commit` to `vlsm` or `split` to permanently reserve the blocks.
```bash
netpulse-subnet vlsm 10.0.0.0/24 --req "HR=100,Dev=50" --commit
```

**Audit Reservations:**
```bash
netpulse-subnet ipam list
```

**Check Available Free Space:**
```bash
netpulse-subnet ipam free 10.0.0.0/23
```

### 8. DNS Export
Automate the generation of Reverse DNS (PTR) records or BIND zone files.

**Generate BIND Zone:**
```bash
netpulse-subnet export-dns 10.0.0.0/24 --format bind --domain internal.local
```

**Export to JSON or CSV:**
```bash
netpulse-subnet export-dns 10.0.0.0/24 --format json --out dns_records.json
```

---

## REST API Usage

You can launch the FastAPI server standalone to expose these tools over HTTP.

```bash
uvicorn netpulse.subnet.api:app --reload --port 8001
```

Navigate to `http://127.0.0.1:8001/docs` in your browser to view the interactive Swagger UI.

### Example `curl` Request

**Calculate Subnet Boundaries:**
```bash
curl -X POST http://127.0.0.1:8001/api/v1/subnet/info \
     -H "Content-Type: application/json" \
     -d '{"ip": "10.0.5.15", "mask_or_prefix": "16"}'
```
