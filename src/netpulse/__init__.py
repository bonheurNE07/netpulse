import sys
import os

# Dynamically add the package subdirectories to sys.path so top-level imports resolve cleanly
package_dir = os.path.dirname(__file__)

if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

for name in ["netpulse_core", "netpulse_engine", "netpulse_cli", "netpulse_api"]:
    subpath = os.path.join(package_dir, name)
    if subpath not in sys.path:
        sys.path.insert(0, subpath)
