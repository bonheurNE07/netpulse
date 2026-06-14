from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from netpulse.subnet.models.subnet import SubnetInfo, VLSMResult
from netpulse.subnet.services.subnet import (
    calculate_subnet_info,
    split_fixed_length,
    allocate_vlsm,
    find_containing_subnet
)
from fastapi import FastAPI

app = FastAPI(title="NetPulse Subnet API")

subnet_router = APIRouter()
class SubnetInfoRequest(BaseModel):
    ip: str = Field(..., description="The IP address to query.", examples=["192.168.1.45"])
    mask_or_prefix: str = Field(..., description="Subnet netmask (e.g. 255.255.255.0) or prefix length (e.g. 24).", examples=["28"])

class SubnetSplitRequest(BaseModel):
    parent_network: str = Field(..., description="Parent CIDR range (e.g., 10.0.0.0/8).", examples=["10.0.0.0/8"])
    subnets_count: Optional[int] = Field(None, description="Number of equal-sized subnets desired.", ge=1)
    hosts_per_subnet: Optional[int] = Field(None, description="Desired usable hosts per subnet partition.", ge=1)

class SubnetVLSMRequest(BaseModel):
    parent_network: str = Field(..., description="Parent IPv4 CIDR network to partition.", examples=["192.168.1.0/24"])
    requirements: List[Dict[str, Any]] = Field(
        ...,
        description="Subnet host requirement parameters (list of objects with label and host count).",
        examples=[[{"name": "HR", "hosts": 120}, {"name": "Dev", "hosts": 50}]]
    )

class SubnetDiscoverRequest(BaseModel):
    ip: str = Field(..., description="IP address to lookup.", examples=["192.168.1.45"])
    subnets: List[str] = Field(..., description="List of subnets in CIDR notation to search in.", examples=[["192.168.1.0/26", "192.168.1.64/26"]])

# 7. Subnet Endpoints
@subnet_router.post("/api/v1/subnet/info", response_model=SubnetInfo, status_code=status.HTTP_200_OK)
def get_subnet_info(req: SubnetInfoRequest):
    """
    Acts as a subnet calculator. Given an IP and mask/prefix, returns detailed boundary configurations.
    """
    try:
        return calculate_subnet_info(req.ip, req.mask_or_prefix)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "InvalidSubnetParameters",
                "message": str(e)
            }
        )

@subnet_router.post("/api/v1/subnet/split", response_model=List[str], status_code=status.HTTP_200_OK)
def split_subnet(req: SubnetSplitRequest):
    """
    Partitions a parent CIDR into equal-sized subnets (FLSM).
    """
    try:
        return split_fixed_length(
            parent_network=req.parent_network,
            subnets_count=req.subnets_count,
            hosts_per_subnet=req.hosts_per_subnet
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "SubnetSplitError",
                "message": str(e)
            }
        )

@subnet_router.post("/api/v1/subnet/vlsm", response_model=VLSMResult, status_code=status.HTTP_200_OK)
def allocate_vlsm_subnets(req: SubnetVLSMRequest):
    """
    Calculates optimal subnet boundaries based on Variable-Length Subnet Masking (VLSM).
    """
    try:
        return allocate_vlsm(req.parent_network, req.requirements)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "VLSMAllocationError",
                "message": str(e)
            }
        )

@subnet_router.post("/api/v1/subnet/discover", status_code=status.HTTP_200_OK)
def discover_containing_subnet(req: SubnetDiscoverRequest):
    """
    Matches a given IP address against a list of subnets to discover which subnet it belongs to.
    """
    try:
        containing = find_containing_subnet(req.ip, req.subnets)
        return {
            "ip": req.ip,
            "containing_subnet": containing
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "SubnetLookupError",
                "message": str(e)
            }
        )

app.include_router(subnet_router)

