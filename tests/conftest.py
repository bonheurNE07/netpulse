import sys
import os

# Dynamically add the package subdirectories to sys.path so tests can import them
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/netpulse"))

if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

for name in ["netpulse_core", "netpulse_engine", "netpulse_cli", "netpulse_api"]:
    subpath = os.path.join(base_dir, name)
    if subpath not in sys.path:
        sys.path.insert(0, subpath)
