import sys
import os
import time
import logging
from typing import List, Optional, Dict, Any
from collections import defaultdict

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from netpulse.core.services.discovery import DiscoveryService
from netpulse.core.models.discovery import DiscoveryMethod, DiscoveryResult
from netpulse.core.services.db import DatabaseService
from netpulse.core.services.drift import DriftService
from netpulse.core.models.drift import DriftResult
from netpulse.core.models.ssh import SshExecutionAudit, SshHostConfig
from netpulse.core.services.ssh_runner import SshRunnerService

# Initialize persistent SQLite storage & drift services
db_service = DatabaseService("netpulse.db")
drift_service = DriftService()
ssh_runner = SshRunnerService(db_service)

# Configure structured logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("netpulse_api")

app = FastAPI(
    title="NetPulse REST API",
    description="High-performance network discovery and analysis REST service powered by Rust.",
    version="0.1.0.4",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 1. CORS Middleware Config
# Reject wildcard origins (*) and explicitly list localhost development endpoints.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # TODO(security): configure production origins here
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 2. Security Headers Middleware
# Inject robust browser headers to enforce strict MIME-type sniffing, frame protections, and CSP.
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com;"
    return response

# 3. Sliding Window Rate Limiting State & Helper
# Strictly enforces a maximum of 5 sweep requests per minute per IP.
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 5
request_history = defaultdict(list)

def check_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    
    # Prune access timestamps older than 60 seconds
    request_history[client_ip] = [t for t in request_history[client_ip] if now - t < RATE_LIMIT_WINDOW]
    
    if len(request_history[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        retry_seconds = int(RATE_LIMIT_WINDOW - (now - request_history[client_ip][0]))
        logger.warning(f"Rate limit exceeded for IP: {client_ip}. Retrying in {retry_seconds}s.")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "RateLimitExceeded",
                "message": f"Too many scan requests. Rate limit is {RATE_LIMIT_MAX_REQUESTS} requests per minute.",
                "retry_after_seconds": retry_seconds
            }
        )
    request_history[client_ip].append(now)

# 4. Request Validation Schema
class ScanRequest(BaseModel):
    target_network: str = Field(
        ..., 
        description="Target CIDR network address range to scan (e.g. 192.168.1.0/24).",
        examples=["192.168.1.0/24"]
    )
    methods: Optional[List[str]] = Field(
        default=["arp"], 
        description="List of protocols to scan: 'arp', 'icmp'.",
        examples=[["arp", "icmp"]]
    )
    timeout_ms: int = Field(
        default=1000, 
        ge=1, 
        le=10000, 
        description="Timeout in milliseconds for responses from each host (1ms to 10000ms)."
    )
    interface: Optional[str] = Field(
        default=None, 
        description="Explicit network interface to bind to (e.g. eth0, wlan0). Only used by ARP."
    )

    @field_validator("target_network")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        import ipaddress
        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid network CIDR format: {e}")
        return v

    @field_validator("methods")
    @classmethod
    def validate_methods(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            valid_methods = {"arp", "icmp"}
            for m in v:
                if m.lower() not in valid_methods:
                    raise ValueError(f"Invalid method '{m}'. Supported methods: 'arp', 'icmp'.")
        return v

# 5. REST Endpoints
@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """
    Light service health check.
    """
    return {
        "status": "healthy",
        "service": "netpulse-api",
        "timestamp": time.time()
    }

@app.post("/api/v1/discover", response_model=DiscoveryResult, status_code=status.HTTP_200_OK)
async def discover(scan_req: ScanRequest, request: Request):
    """
    Executes a high-performance network discovery scan.
    Requires elevated systems-level privileges on the server unless running in NETPULSE_MOCK=1 mode.
    """
    # Enforce rate-limiting
    check_rate_limit(request)
    
    # Parse methods into domain-model enums
    valid_methods = {"arp": DiscoveryMethod.ARP, "icmp": DiscoveryMethod.ICMP}
    parsed_methods = []
    if scan_req.methods:
        for m in scan_req.methods:
            parsed_methods.append(valid_methods[m.lower()])
    else:
        parsed_methods = [DiscoveryMethod.ARP]

    logger.info(
        f"Initiating scan from IP {request.client.host if request.client else 'unknown'} "
        f"on {scan_req.target_network} using methods: {[m.value for m in parsed_methods]}."
    )

    # Execute orchestrator service call
    try:
        service = DiscoveryService()
        result = await service.discover_network(
            target_network=scan_req.target_network,
            methods=parsed_methods,
            timeout_ms=scan_req.timeout_ms,
            interface=scan_req.interface
        )
    except Exception as e:
        logger.exception("Internal orchestration error during network sweep")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "OrchestrationError",
                "message": f"Orchestration failure during network sweep: {e}"
            }
        )

    # Handle low-level raw socket permission issues cleanly
    is_permission_error = False
    permission_err_msg = ""
    for err in result.errors:
        if "permission denied" in err.lower() or "operation not permitted" in err.lower():
            is_permission_error = True
            permission_err_msg = err
            break

    if is_permission_error:
        method_names = ", ".join(m.value for m in parsed_methods)
        logger.error(f"Scan failed due to lack of raw socket permissions on the host: {permission_err_msg}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "PrivilegeError",
                "message": "NetPulse server requires elevated privileges to generate raw sockets.",
                "details": permission_err_msg,
                "remediation": {
                    "sudo_run": f"sudo .venv/bin/python -m uvicorn netpulse_api.main:app --host 127.0.0.1 --port 8000",
                    "setcap_grant": "sudo setcap cap_net_raw,cap_net_admin+eip $(readlink -f .venv/bin/python)",
                    "mock_mode": "Set environment variable NETPULSE_MOCK=1 to run safely without root privileges."
                }
            }
        )

    # Automatically persist completed scans in history
    try:
        db_service.save_scan(result)
    except Exception as db_err:
        logger.error(f"Failed to persist discovery scan to history database: {db_err}")

    # Return Pydantic object directly; FastAPI encodes cleanly
    return result

try:
    from netpulse.subnet.api import subnet_router
    app.include_router(subnet_router)
except ImportError:
    pass

# 8. SQLite Storage & Network Drift Request Models
class ScanCompareRequest(BaseModel):
    scan_id_old: str = Field(..., description="UUID of the old benchmark scan.", examples=["7b86da45-ad65-4b55-b200-92a41a71a998"])
    scan_id_new: str = Field(..., description="UUID of the new comparison scan.", examples=["9f164b38-2d88-4fb3-a912-1d542a17cb45"])


# 9. SQLite Storage & Network Drift Endpoints
@app.get("/api/v1/scans", response_model=List[Dict[str, Any]], status_code=status.HTTP_200_OK)
def get_scans_history(network: Optional[str] = None):
    """
    Retrieves the list of all past discovery scan summaries. Supports filtering by target CIDR network block.
    """
    try:
        return db_service.get_scan_history(network)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "DatabaseError",
                "message": f"Failed to retrieve scan history: {e}"
            }
        )

@app.get("/api/v1/scans/{scan_id}", response_model=DiscoveryResult, status_code=status.HTTP_200_OK)
def get_scan_by_id(scan_id: str):
    """
    Fetches the complete results of a specific scan session by its UUID.
    """
    try:
        scan_res = db_service.get_scan(scan_id)
        if not scan_res:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "ScanNotFound",
                    "message": f"Scan with ID '{scan_id}' not found in local database."
                }
            )
        return scan_res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "DatabaseError",
                "message": f"Failed to retrieve scan: {e}"
            }
        )

@app.post("/api/v1/discover/drift", response_model=DriftResult, status_code=status.HTTP_200_OK)
async def discover_network_drift(scan_req: ScanRequest, request: Request):
    """
    Executes a new discovery sweep, compares it against the most recent saved completed sweep on that network,
    calculates drift statistics, saves the new run, and returns the comprehensive analysis.
    """
    # Enforce rate-limiting for active network scans
    check_rate_limit(request)

    # 1. Fetch benchmark baseline
    try:
        baseline = db_service.get_latest_scan(scan_req.target_network)
    except Exception as db_err:
        logger.error(f"Failed to fetch baseline scan from database: {db_err}")
        baseline = None

    # 2. Run new sweep
    valid_methods = {"arp": DiscoveryMethod.ARP, "icmp": DiscoveryMethod.ICMP}
    parsed_methods = []
    if scan_req.methods:
        for m in scan_req.methods:
            parsed_methods.append(valid_methods[m.lower()])
    else:
        parsed_methods = [DiscoveryMethod.ARP]

    try:
        service = DiscoveryService()
        new_result = await service.discover_network(
            target_network=scan_req.target_network,
            methods=parsed_methods,
            timeout_ms=scan_req.timeout_ms,
            interface=scan_req.interface
        )
    except Exception as e:
        logger.exception("Internal orchestration error during network sweep")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "OrchestrationError",
                "message": f"Orchestration failure during network sweep: {e}"
            }
        )

    # Handle privileges errors
    is_permission_error = False
    permission_err_msg = ""
    for err in new_result.errors:
        if "permission denied" in err.lower() or "operation not permitted" in err.lower():
            is_permission_error = True
            permission_err_msg = err
            break

    if is_permission_error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "PrivilegeError",
                "message": "NetPulse server requires elevated privileges to generate raw sockets.",
                "details": permission_err_msg
            }
        )

    # 3. Calculate drift
    try:
        drift_res = drift_service.calculate_drift(new_result, baseline)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "DriftCalculationError",
                "message": f"Failed to compute network drift: {e}"
            }
        )

    # 4. Save new result to history database
    try:
        db_service.save_scan(new_result)
    except Exception as db_err:
        logger.error(f"Failed to persist new scan run to history database: {db_err}")

    return drift_res

@app.post("/api/v1/scans/compare", response_model=DriftResult, status_code=status.HTTP_200_OK)
def compare_historic_scans(req: ScanCompareRequest):
    """
    Directly compares two existing historical scans in the database.
    """
    try:
        old_scan = db_service.get_scan(req.scan_id_old)
        if not old_scan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "ScanNotFound",
                    "message": f"Baseline scan with ID '{req.scan_id_old}' not found."
                }
            )

        new_scan = db_service.get_scan(req.scan_id_new)
        if not new_scan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "ScanNotFound",
                    "message": f"Comparison scan with ID '{req.scan_id_new}' not found."
                }
            )

        return drift_service.calculate_drift(new_scan, old_scan)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "ComparisonError",
                "message": f"Failed to compare scans: {e}"
            }
        )


# 5. SSH Request Schemas & Endpoints

class SshExecuteHost(BaseModel):
    ip: str = Field(..., description="Target IP or hostname.")
    port: int = Field(22, description="SSH port.")

class SshExecuteRequest(BaseModel):
    hosts: List[SshExecuteHost] = Field(..., description="List of SSH hosts.")
    command: str = Field(..., description="SSH command to execute.")
    username: str = Field(..., description="SSH login username.")
    password: Optional[str] = Field(None, description="SSH login password.")
    enable_password: Optional[str] = Field(None, description="Cisco enable password.")
    auto_negotiate: bool = Field(True, description="Enable key-exchange auto-negotiate fallbacks.")
    ignore_host_keys: bool = Field(True, description="Ignore host verification checks.")
    timeout_seconds: int = Field(10, description="Connection timeout.")

@app.post("/api/v1/ssh/execute", response_model=SshExecutionAudit, status_code=status.HTTP_200_OK)
async def execute_ssh_command(req: SshExecuteRequest):
    """
    Executes a command concurrently across one or multiple remote SSH hosts.
    Resolves legacy algorithms and caches results automatically.
    """
    try:
        hosts_config = []
        for h in req.hosts:
            hosts_config.append(SshHostConfig(
                ip=h.ip,
                port=h.port,
                username=req.username,
                password=req.password,
                enable_password=req.enable_password,
                auto_negotiate=req.auto_negotiate,
                ignore_host_keys=req.ignore_host_keys,
                timeout_seconds=req.timeout_seconds
            ))
            
        audit = await ssh_runner.execute_concurrently(hosts_config, req.command)
        return audit
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "SshExecutionError",
                "message": f"Concurrent SSH runner failed: {e}"
            }
        )

@app.get("/api/v1/ssh/history", response_model=List[Dict[str, Any]], status_code=status.HTTP_200_OK)
def get_ssh_execution_history():
    """
    Queries basic logs for all historical concurrent SSH runs.
    """
    try:
        return db_service.get_ssh_history()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "HistoryError",
                "message": f"Failed to retrieve SSH history: {e}"
            }
        )
