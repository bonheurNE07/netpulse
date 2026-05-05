import sys
import os
import uuid
from datetime import datetime, timezone, timedelta

# Add the packages/core to sys.path to import the model
sys.path.append(os.path.join(os.getcwd(), "packages/core"))

try:
    from netpulse_core.models.device import Device, DeviceStatus
    from netpulse_core.models.discovery import DiscoveryResult, DiscoveryMethod
except ImportError as e:
    print(f"Error: {e}")
    print("Please install pydantic: pip install pydantic")
    sys.exit(1)

def test_discovery_result():
    print("--- Testing Refined DiscoveryResult Model ---")
    
    start = datetime.now(timezone.utc)
    end = start + timedelta(seconds=15)
    
    # 1. Create a discovery result
    try:
        result = DiscoveryResult(
            network="192.168.1.0/24",
            methods=[DiscoveryMethod.ARP, DiscoveryMethod.ICMP],
            status="completed",
            started_at=start,
            finished_at=end,
            devices=[
                Device(ip="192.168.1.1", status=DeviceStatus.UP),
                Device(ip="192.168.1.2", status=DeviceStatus.UP),
                Device(ip="192.168.1.3", status=DeviceStatus.DOWN)
            ],
            stats={"scanned": 254, "responsive": 2},
            errors=["Timeout on 192.168.1.5"]
        )
        
        print(f"SUCCESS: Created discovery result for {result.network}")
        print(f"Methods: {result.methods}")
        print(f"Duration: {result.duration_s}s")
        print(f"Total Discovered (UP): {result.total_discovered}")
        
        # Verify JSON
        print("\nJSON Data Sample:")
        print(result.model_dump_json(indent=2))
        
    except Exception as e:
        print(f"FAILURE: {e}")

if __name__ == "__main__":
    test_discovery_result()
