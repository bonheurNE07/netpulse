import uuid
from typing import Optional
from datetime import datetime, timezone

from netpulse.core.models.device import Device, DeviceStatus
from netpulse.core.models.discovery import DiscoveryResult
from netpulse.core.models.drift import DeviceChange, DriftResult


class DriftService:
    """
    Computes differences between network sweeps to detect active host status drift.
    """

    def calculate_drift(
        self,
        new_scan: DiscoveryResult,
        old_scan: Optional[DiscoveryResult] = None
    ) -> DriftResult:
        """
        Compares a target sweep against a saved baseline sweep.
        Classifies active hosts into joined, left, modified, and unchanged cohorts.
        """
        new_timestamp_iso = new_scan.finished_at.isoformat() if hasattr(new_scan.finished_at, "isoformat") else str(new_scan.finished_at)

        # First scan case: old_scan is None
        if not old_scan:
            return DriftResult(
                network=str(new_scan.network),
                old_scan_id=None,
                new_scan_id=new_scan.id,
                old_timestamp=None,
                new_timestamp=new_timestamp_iso,
                joined=new_scan.devices,
                left=[],
                modified=[],
                unchanged=[]
            )

        old_timestamp_iso = old_scan.finished_at.isoformat() if hasattr(old_scan.finished_at, "isoformat") else str(old_scan.finished_at)

        # Create dictionaries keyed by IP for rapid lookup
        # Only active ("up") devices are counted for baseline comparisons
        old_devices = {str(d.ip): d for d in old_scan.devices if d.status == DeviceStatus.UP}
        new_devices = {str(d.ip): d for d in new_scan.devices if d.status == DeviceStatus.UP}

        joined_list = []
        left_list = []
        modified_list = []
        unchanged_list = []

        # 1. Detect Joined & Modified hosts
        for ip, new_dev in new_devices.items():
            if ip not in old_devices:
                # Host was not active previously
                joined_list.append(new_dev)
            else:
                old_dev = old_devices[ip]
                # Check for MAC address drift (signals IP reassignment or potential spoofing)
                if old_dev.mac != new_dev.mac:
                    modified_list.append(DeviceChange(
                        ip=ip,
                        mac_old=old_dev.mac,
                        mac_new=new_dev.mac,
                        rtt_old=old_dev.rtt_ms,
                        rtt_new=new_dev.rtt_ms,
                        status_old=old_dev.status.value if hasattr(old_dev.status, "value") else str(old_dev.status),
                        status_new=new_dev.status.value if hasattr(new_dev.status, "value") else str(new_dev.status)
                    ))
                else:
                    # Unchanged state
                    unchanged_list.append(new_dev)

        # 2. Detect Left hosts (offline or missing)
        for ip, old_dev in old_devices.items():
            if ip not in new_devices:
                # Host was active in baseline but did not respond now
                left_list.append(old_dev)

        return DriftResult(
            network=str(new_scan.network),
            old_scan_id=old_scan.id,
            new_scan_id=new_scan.id,
            old_timestamp=old_timestamp_iso,
            new_timestamp=new_timestamp_iso,
            joined=joined_list,
            left=left_list,
            modified=modified_list,
            unchanged=unchanged_list
        )
