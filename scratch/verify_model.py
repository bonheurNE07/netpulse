import sys
import os
import uuid
from datetime import datetime, timezone

# Add the packages/core to sys.path to import the model
sys.path.append(os.path.join(os.getcwd(), "packages/core"))

try:
    from netpulse_core.models.device import Device, DeviceStatus
except ImportError as e:
    print(f"Error: {e}")
    print("Please install pydantic: pip install pydantic")
    sys.exit(1)

def test_device_model_v2():
    print("--- Testing Refactored Device Model ---")
    
    # 1. Valid device creation
    try:
        device = Device(
            ip="192.168.1.1",
            mac="00:11:22:33:44:55",
            hostname="gateway.local",
            status=DeviceStatus.UP,
            rtt_ms=0.5,
            metadata={"source": "uv_validated"}
        )
        print(f"SUCCESS: Created device with ID: {device.id}")
        print(f"Timestamp (UTC): {device.created_at}")
        
        # Verify JSON schema output
        print("\nJSON Data Sample:")
        print(device.model_dump_json(indent=2))
        
    except Exception as e:
        print(f"FAILURE: Could not create valid device: {e}")

    # 2. Assignment Validation check
    print("\n--- Testing Assignment Validation ---")
    try:
        device = Device(ip="10.0.0.1")
        device.ip = "not-an-ip" # Should trigger validation error
        print("FAILURE: Accepted an invalid IP during assignment")
    except Exception as e:
        print(f"SUCCESS: Assignment validation caught error: {type(e).__name__}")

    # 3. UUID Consistency
    print("\n--- Testing UUID Consistency ---")
    d1 = Device(ip="1.1.1.1")
    d2 = Device(ip="1.1.1.1")
    if d1.id != d2.id:
        print(f"SUCCESS: Generated unique UUIDs: {d1.id} vs {d2.id}")
    else:
        print("FAILURE: UUID collision detected")

if __name__ == "__main__":
    test_device_model_v2()
