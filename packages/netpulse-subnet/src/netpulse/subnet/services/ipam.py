import sqlite3
import os
from typing import List, Dict, Any
import ipaddress

def _get_db_path() -> str:
    return os.environ.get("NETPULSE_IPAM_DB", ".netpulse-ipam.db")

def get_connection():
    """Returns a connection to the IPAM SQLite database."""
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"IPAM database not found at '{db_path}'. Run 'netpulse-subnet ipam init' first.")
    return sqlite3.connect(db_path)

def init_db():
    """Initializes the local SQLite database for IPAM tracking."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subnets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            network TEXT NOT NULL UNIQUE,
            description TEXT,
            parent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_reservation(network: str, description: str, parent: str):
    """Adds a CIDR block to the IPAM database."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO subnets (network, description, parent) VALUES (?, ?, ?)",
            (network, description, parent)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Ignore if it's already reserved
        pass
    finally:
        conn.close()

def get_reservations() -> List[Dict[str, Any]]:
    """Retrieves all allocated subnet blocks."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, network, description, parent, created_at FROM subnets ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "id": row[0],
            "network": row[1],
            "description": row[2],
            "parent": row[3],
            "created_at": row[4]
        }
        for row in rows
    ]

def get_reservations_for_parent(parent_network: str) -> List[str]:
    """Retrieves networks that are subnets of the provided parent block."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT network FROM subnets")
    rows = cursor.fetchall()
    conn.close()
    
    try:
        parent_net = ipaddress.ip_network(parent_network, strict=False)
    except ValueError:
        return []
        
    reserved = []
    for row in rows:
        try:
            net = ipaddress.ip_network(row[0], strict=False)
            # If the database network falls within the requested parent bounds
            if net.subnet_of(parent_net):
                reserved.append(str(net))
        except ValueError:
            continue
            
    return reserved
