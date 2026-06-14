# Usage Guide

`netpulse-subnet` provides both a beautiful Terminal User Interface (CLI) and a REST API. 

## CLI Usage

If you installed the package via `pip` or `uv`, the `netpulse-subnet` command is immediately available in your terminal.

### 1. Subnet Info (Calculator)
Retrieve detailed binary alignments, masks, and boundaries for any IP/CIDR.
```bash
netpulse-subnet info 192.168.1.50/24
```

### 2. Subnet Splitter (FLSM)
Split a massive network block into smaller, equal-sized subnets.

**By number of subnets:**
```bash
netpulse-subnet split 10.0.0.0/8 --subnets 4
```
**By required hosts per subnet:**
```bash
netpulse-subnet split 10.0.0.0/8 --hosts 2000
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
