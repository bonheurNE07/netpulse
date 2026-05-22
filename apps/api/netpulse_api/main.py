import sys
import os
import time
import logging
from typing import List, Optional
from collections import defaultdict

# Dynamically add the packages folder paths so we can import them from anywhere
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.insert(0, os.path.join(base_dir, "packages/core"))
sys.path.insert(0, os.path.join(base_dir, "packages/engine"))

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from netpulse_core.services.discovery import DiscoveryService
from netpulse_core.models.discovery import DiscoveryMethod, DiscoveryResult

# Configure structured logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("netpulse_api")

app = FastAPI(
    title="NetPulse REST API",
    description="High-performance network discovery and analysis REST service powered by Rust.",
    version="0.1.0",
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
    response.headers["Content-Security-Policy"] = "default-src 'self';"
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

    # Return Pydantic object directly; FastAPI encodes cleanly
    return result
