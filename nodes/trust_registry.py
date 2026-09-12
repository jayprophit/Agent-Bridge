"""TrustRegistry (v0.7). Node trust and pairing management.

Manages trust relationships between nodes for secure cross-device coordination.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from nodes.node_descriptor import (
    OWNER_NODE, TRUSTED_NODE, LIMITED_NODE, UNTRUSTED_NODE,
    TRUST_LEVELS,
)


@dataclass
class TrustRecord:
    """Record of trust relationship between nodes."""
    node_id: str
    trust_level: str = UNTRUSTED_NODE
    paired_at: float | None = None
    last_verified: float | None = None
    capabilities_verified: list[str] = field(default_factory=list)
    notes: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrustRegistry:
    """Registry of trust relationships between nodes.
    
    Trust levels:
    - OWNER_NODE: This device (highest trust)
    - TRUSTED_NODE: Explicitly paired and verified node
    - LIMITED_NODE: Known node with limited capabilities
    - UNTRUSTED_NODE: Unknown or unverified node (default)
    
    Discovery does NOT imply trust. Nodes must be explicitly paired.
    """
    
    def __init__(self, local_node_id: str):
        self.local_node_id = local_node_id
        self._trust_records: dict[str, TrustRecord] = {}
        
        # Local node is always OWNER_NODE
        self._trust_records[local_node_id] = TrustRecord(
            node_id=local_node_id,
            trust_level=OWNER_NODE,
            paired_at=time.monotonic(),
            last_verified=time.monotonic(),
        )
    
    def get_trust_level(self, node_id: str) -> str:
        """Get trust level for a node."""
        if node_id == self.local_node_id:
            return OWNER_NODE
        record = self._trust_records.get(node_id)
        return record.trust_level if record else UNTRUSTED_NODE
    
    def is_trusted(self, node_id: str, min_level: str = TRUSTED_NODE) -> bool:
        """Check if node meets minimum trust level."""
        node_trust = self.get_trust_level(node_id)
        trust_priority = {
            OWNER_NODE: 4,
            TRUSTED_NODE: 3,
            LIMITED_NODE: 2,
            UNTRUSTED_NODE: 1,
        }
        return trust_priority.get(node_trust, 0) >= trust_priority.get(min_level, 0)
    
    def pair_node(self, node_id: str, trust_level: str = TRUSTED_NODE,
                  capabilities_verified: list[str] | None = None,
                  notes: str = "") -> TrustRecord:
        """Explicitly pair with a node.
        
        Args:
            node_id: Node to pair with
            trust_level: Trust level to assign (default TRUSTED_NODE)
            capabilities_verified: List of capabilities verified during pairing
            notes: Optional notes about the pairing
            
        Returns:
            The created/updated TrustRecord
        """
        if trust_level not in TRUST_LEVELS:
            raise ValueError(f"Invalid trust level: {trust_level}")
        
        record = self._trust_records.get(node_id)
        if record:
            record.trust_level = trust_level
            record.last_verified = time.monotonic()
            if capabilities_verified:
                record.capabilities_verified = capabilities_verified
            record.notes = notes
        else:
            record = TrustRecord(
                node_id=node_id,
                trust_level=trust_level,
                paired_at=time.monotonic(),
                last_verified=time.monotonic(),
                capabilities_verified=capabilities_verified or [],
                notes=notes,
            )
            self._trust_records[node_id] = record
        
        return record
    
    def unpair_node(self, node_id: str) -> bool:
        """Remove trust relationship with a node.
        
        Args:
            node_id: Node to unpair
            
        Returns:
            True if node was unpaired, False if not found
        """
        if node_id == self.local_node_id:
            return False  # Cannot unpair self
        
        if node_id in self._trust_records:
            del self._trust_records[node_id]
            return True
        return False
    
    def downgrade_trust(self, node_id: str, reason: str = "") -> TrustRecord | None:
        """Downgrade trust level for a node (e.g., after failed verification)."""
        if node_id == self.local_node_id:
            return None
        
        record = self._trust_records.get(node_id)
        if record:
            if record.trust_level == TRUSTED_NODE:
                record.trust_level = LIMITED_NODE
            elif record.trust_level == LIMITED_NODE:
                record.trust_level = UNTRUSTED_NODE
            record.notes = f"{record.notes}; Downgraded: {reason}".strip("; ")
            record.last_verified = time.monotonic()
        return record
    
    def get_trusted_nodes(self, min_level: str = TRUSTED_NODE) -> list[str]:
        """Get list of node IDs that meet minimum trust level."""
        trust_priority = {
            OWNER_NODE: 4,
            TRUSTED_NODE: 3,
            LIMITED_NODE: 2,
            UNTRUSTED_NODE: 1,
        }
        min_priority = trust_priority.get(min_level, 0)
        return [
            node_id for node_id, record in self._trust_records.items()
            if trust_priority.get(record.trust_level, 0) >= min_priority
        ]
    
    def get_all_records(self) -> list[TrustRecord]:
        """Get all trust records."""
        return list(self._trust_records.values())
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize trust registry for storage."""
        return {
            "local_node_id": self.local_node_id,
            "records": {nid: rec.to_dict() for nid, rec in self._trust_records.items()},
        }


def create_trust_registry(local_node_id: str) -> TrustRegistry:
    """Factory to create a TrustRegistry."""
    return TrustRegistry(local_node_id)