import sqlite3
import json
import uuid
import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from netpulse.core.models.device import Device, DeviceStatus
from netpulse.core.models.discovery import DiscoveryResult, DiscoveryMethod
from netpulse.core.models.ssh import SshExecutionAudit


class DatabaseService:
    """
    Handles persistence of discovery sweeps and hosts in SQLite.
    Employs lightweight Python sqlite3 connections to maintain zero-dependency speed.
    """

    def __init__(self, db_path: str = "netpulse.db"):
        self.db_path = db_path
        self._conn = None
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # Enable Foreign Key enforcement in SQLite
            self._conn.execute("PRAGMA foreign_keys = ON;")
        return self._conn

    def init_db(self):
        """
        Creates scans and devices tables if they do not exist.
        """
        # Ensure parent directories exist
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        with self._get_connection() as conn:
            # 1. Scans Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    id TEXT PRIMARY KEY,
                    network TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    scanned_count INTEGER NOT NULL,
                    responsive_count INTEGER NOT NULL,
                    methods TEXT NOT NULL,
                    errors TEXT NOT NULL,
                    stats TEXT,
                    metadata TEXT
                );
            """)

            # 2. Devices Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    scan_id TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    mac TEXT,
                    hostname TEXT,
                    vendor TEXT,
                    status TEXT NOT NULL,
                    rtt_ms REAL,
                    created_at TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY (scan_id) REFERENCES scans (id) ON DELETE CASCADE
                );
            """)
            
            # 3. SSH Audit Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ssh_audit (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    targets TEXT NOT NULL,
                    success_count INTEGER NOT NULL,
                    failed_count INTEGER NOT NULL,
                    executed_at TEXT NOT NULL,
                    results TEXT NOT NULL
                );
            """)
            
            # Create indexes for rapid subnet history queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scans_network ON scans (network);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_scan_id ON devices (scan_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices (ip);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ssh_audit_executed_at ON ssh_audit (executed_at);")
            conn.commit()

    def save_scan(self, result: DiscoveryResult):
        """
        Saves a scan and all discovered active devices inside a transaction.
        """
        methods_str = ",".join(m.value if hasattr(m, "value") else str(m) for m in result.methods)
        errors_str = json.dumps(result.errors)
        stats_str = json.dumps(result.stats)
        metadata_str = json.dumps(result.metadata)

        started_iso = result.started_at.isoformat() if hasattr(result.started_at, "isoformat") else str(result.started_at)
        finished_iso = result.finished_at.isoformat() if hasattr(result.finished_at, "isoformat") else str(result.finished_at)

        with self._get_connection() as conn:
            # Insert scan metadata
            conn.execute(
                """
                INSERT INTO scans (
                    id, network, status, started_at, finished_at,
                    scanned_count, responsive_count, methods, errors, stats, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(result.id),
                    str(result.network),
                    result.status,
                    started_iso,
                    finished_iso,
                    result.stats.get("scanned", 0),
                    result.total_discovered,
                    methods_str,
                    errors_str,
                    stats_str,
                    metadata_str
                )
            )

            # Insert discovered devices
            for device in result.devices:
                device_metadata_str = json.dumps(device.metadata)
                created_iso = device.created_at.isoformat() if hasattr(device.created_at, "isoformat") else str(device.created_at)
                last_seen_iso = device.last_seen.isoformat() if hasattr(device.last_seen, "isoformat") else str(device.last_seen)

                conn.execute(
                    """
                    INSERT INTO devices (
                        id, scan_id, ip, mac, hostname, vendor,
                        status, rtt_ms, created_at, last_seen, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        str(device.id),
                        str(result.id),
                        str(device.ip),
                        device.mac,
                        device.hostname,
                        device.vendor,
                        device.status.value if hasattr(device.status, "value") else str(device.status),
                        device.rtt_ms,
                        created_iso,
                        last_seen_iso,
                        device_metadata_str
                    )
                )
            conn.commit()

    def get_scan(self, scan_id: str) -> Optional[DiscoveryResult]:
        """
        Retrieves a full DiscoveryResult model populated with its devices from database.
        """
        with self._get_connection() as conn:
            scan_row = conn.execute("SELECT * FROM scans WHERE id = ?;", (scan_id,)).fetchone()
            if not scan_row:
                return None

            device_rows = conn.execute("SELECT * FROM devices WHERE scan_id = ?;", (scan_id,)).fetchall()

        # Rebuild devices Pydantic objects
        devices = []
        for dev in device_rows:
            try:
                # Convert timestamps safely
                c_at = datetime.fromisoformat(dev["created_at"])
                l_seen = datetime.fromisoformat(dev["last_seen"])
            except Exception:
                c_at = datetime.now(timezone.utc)
                l_seen = datetime.now(timezone.utc)

            devices.append(Device(
                id=uuid.UUID(dev["id"]),
                ip=dev["ip"],
                mac=dev["mac"],
                hostname=dev["hostname"],
                vendor=dev["vendor"],
                status=DeviceStatus(dev["status"]),
                rtt_ms=dev["rtt_ms"],
                created_at=c_at,
                last_seen=l_seen,
                metadata=json.loads(dev["metadata"]) if dev["metadata"] else {}
            ))

        # Rebuild main DiscoveryResult
        try:
            started = datetime.fromisoformat(scan_row["started_at"])
            finished = datetime.fromisoformat(scan_row["finished_at"])
        except Exception:
            started = datetime.now(timezone.utc)
            finished = datetime.now(timezone.utc)

        methods = []
        if scan_row["methods"]:
            for m in scan_row["methods"].split(","):
                if m.strip():
                    methods.append(DiscoveryMethod(m.strip()))

        return DiscoveryResult(
            id=uuid.UUID(scan_row["id"]),
            network=scan_row["network"],
            methods=methods,
            status=scan_row["status"],
            errors=json.loads(scan_row["errors"]) if scan_row["errors"] else [],
            devices=devices,
            started_at=started,
            finished_at=finished,
            stats=json.loads(scan_row["stats"]) if scan_row["stats"] else {},
            metadata=json.loads(scan_row["metadata"]) if scan_row["metadata"] else {}
        )

    def get_latest_scan(self, network: str) -> Optional[DiscoveryResult]:
        """
        Fetches the most recent completed scan for the specified network block CIDR.
        """
        with self._get_connection() as conn:
            # First match exact or strict subnet matches
            row = conn.execute(
                "SELECT id FROM scans WHERE network = ? AND status = 'completed' ORDER BY started_at DESC LIMIT 1;",
                (network,)
            ).fetchone()
            
            # If no exact match, fallback to any completed scan on that network
            if not row:
                row = conn.execute(
                    "SELECT id FROM scans WHERE network = ? ORDER BY started_at DESC LIMIT 1;",
                    (network,)
                ).fetchone()

        if not row:
            return None
        return self.get_scan(row["id"])

    def get_scan_history(self, network: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Queries basic statistics for all historical scans.
        """
        query = "SELECT * FROM scans"
        params = []
        if network:
            query += " WHERE network = ?"
            params.append(network)
        query += " ORDER BY started_at DESC;"

        history = []
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                history.append({
                    "id": r["id"],
                    "network": r["network"],
                    "status": r["status"],
                    "started_at": r["started_at"],
                    "finished_at": r["finished_at"],
                    "scanned_count": r["scanned_count"],
                    "responsive_count": r["responsive_count"],
                    "methods": r["methods"].split(",") if r["methods"] else [],
                })
        return history

    def save_ssh_audit(self, audit: SshExecutionAudit):
        """
        Saves a multi-host SSH execution audit record to the SQLite database.
        """
        targets_str = ",".join(audit.targets)
        results_list = []
        for res in audit.results:
            results_list.append({
                "ip": res.ip,
                "status": res.status,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "latency_ms": res.latency_ms,
                "negotiated_kex": res.negotiated_kex,
                "negotiated_cipher": res.negotiated_cipher,
                "error_message": res.error_message
            })
        results_str = json.dumps(results_list)
        executed_iso = audit.executed_at.isoformat() if hasattr(audit.executed_at, "isoformat") else str(audit.executed_at)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ssh_audit (
                    id, command, targets, success_count, failed_count, executed_at, results
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(audit.id),
                    audit.command,
                    targets_str,
                    audit.success_count,
                    audit.failed_count,
                    executed_iso,
                    results_str
                )
            )
            conn.commit()

    def get_ssh_history(self) -> List[Dict[str, Any]]:
        """
        Queries and returns all historical SSH executions.
        """
        history = []
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM ssh_audit ORDER BY executed_at DESC;").fetchall()
            for r in rows:
                history.append({
                    "id": r["id"],
                    "command": r["command"],
                    "targets": r["targets"].split(",") if r["targets"] else [],
                    "success_count": r["success_count"],
                    "failed_count": r["failed_count"],
                    "executed_at": r["executed_at"],
                    "results": json.loads(r["results"]) if r["results"] else []
                })
        return history

    def clear_history(self):
        """
        Helper to wipe the SQLite tables (useful for unit testing setups).
        """
        with self._get_connection() as conn:
            conn.execute("DELETE FROM devices;")
            conn.execute("DELETE FROM scans;")
            conn.execute("DELETE FROM ssh_audit;")
            conn.commit()
