from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from prometheus_client import Counter, Gauge

# Prometheus Metrics
ACTIVE_DEVICES = Gauge('netpulse_active_devices_total', 'Total number of active devices on the network')
AVERAGE_RTT = Gauge('netpulse_average_rtt_ms', 'Average ping latency across the subnet')
SCANS_TOTAL = Counter('netpulse_scans_total', 'Total number of scans performed')

from netpulse.discovery.services.discovery import DiscoveryService
from netpulse.discovery.models.discovery import DiscoveryResult, DiscoveryMethod
from netpulse.discovery.services.drift import DriftService
from netpulse.discovery.models.drift import DriftResult

discovery_router = APIRouter(prefix="/discovery", tags=["Discovery"])

class ScanRequest(BaseModel):
    target: str
    timeout_ms: int = 1000

@discovery_router.post("/scan", response_model=DiscoveryResult)
async def scan_network(req: ScanRequest):
    service = DiscoveryService()
    try:
        result = await service.discover_network(req.target, [DiscoveryMethod.ARP], req.timeout_ms)
        
        # Update metrics
        SCANS_TOTAL.inc()
        ACTIVE_DEVICES.set(len(result.devices))
        if result.devices:
            avg_rtt = sum(d.rtt_ms for d in result.devices if d.rtt_ms is not None) / len(result.devices)
            AVERAGE_RTT.set(avg_rtt)
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ScanCompareRequest(BaseModel):
    scan_old: DiscoveryResult
    scan_new: DiscoveryResult

@discovery_router.post("/drift/compare", response_model=DriftResult)
def compare_scans(req: ScanCompareRequest):
    """Statelessly compare two complete discovery scans to calculate drift."""
    service = DriftService()
    try:
        return service.calculate_drift(new_scan=req.scan_new, old_scan=req.scan_old)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ScanDriftRequest(BaseModel):
    target: str
    timeout_ms: int = 1000
    scan_old: DiscoveryResult

@discovery_router.post("/drift/scan", response_model=DriftResult)
async def scan_and_compare(req: ScanDriftRequest):
    """Run a live sweep and instantly compare it against the provided baseline scan."""
    discovery_service = DiscoveryService()
    drift_service = DriftService()
    try:
        new_scan = await discovery_service.discover_network(req.target, [DiscoveryMethod.ARP], req.timeout_ms)
        
        # Update metrics
        SCANS_TOTAL.inc()
        ACTIVE_DEVICES.set(len(new_scan.devices))
        if new_scan.devices:
            avg_rtt = sum(d.rtt_ms for d in new_scan.devices if d.rtt_ms is not None) / len(new_scan.devices)
            AVERAGE_RTT.set(avg_rtt)
            
        return drift_service.calculate_drift(new_scan=new_scan, old_scan=req.scan_old)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
