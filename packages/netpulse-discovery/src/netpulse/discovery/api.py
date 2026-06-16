from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from netpulse.discovery.services.discovery import DiscoveryService
from netpulse.discovery.models.discovery import DiscoveryResult, DiscoveryMethod

discovery_router = APIRouter(prefix="/discovery", tags=["Discovery"])

class ScanRequest(BaseModel):
    target: str
    timeout_ms: int = 1000

@discovery_router.post("/scan", response_model=DiscoveryResult)
async def scan_network(req: ScanRequest):
    service = DiscoveryService()
    try:
        return await service.discover_network(req.target, [DiscoveryMethod.ARP], req.timeout_ms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
