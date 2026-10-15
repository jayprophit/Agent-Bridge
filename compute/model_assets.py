"""Model asset lifecycle (V2 H11, AT-32, maps A05/B01/B05-B06).

H11 requirement: Preserve the first-party Aetherius model runtime and
model-hub direction: discovery, lawful download/hosting, versioned weights,
checksums, compatibility, quantisation, lifecycle management, inference
and serving.

Key rules:
- Every model is a versioned asset with capability tests (§3)
- A marketing model family name is NOT enough to identify weights (§3)
- Fine-tuning/evaluation tracks only where compute/licence/data/quality permit (§2)
- Model changes are auditable (upgrade/rollback records §3)
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# --- model lifecycle states ------------------------------------------------------------------

class ModelAssetState(str, Enum):
    """Lifecycle states for a model asset (§1)."""
    DISCOVERED = "discovered"          # found in registry, not downloaded
    DOWNLOADING = "downloading"        # being fetched
    HOSTED = "hosted"                 # downloaded, checksummed, available
    TESTING = "testing"                # capability tests running
    SERVING = "serving"                # actively serving inference
    DEPRECATED = "deprecated"          # superseded by newer version
    RETIRED = "retired"               # removed from service
    QUARANTINED = "quarantined"       # failed capability tests or licence issue


# --- capability tags (§1) ------------------------------------------------------------------------

class ModelCapability(str, Enum):
    """What a model can do (§1)."""
    CODING = "coding"
    REASONING = "reasoning"
    VISION = "vision"
    EMBEDDING = "embedding"
    TOOL_CALLS = "tool_calls"
    LONG_CONTEXT = "long_context"
    INSTRUCT_FOLLOWING = "instruct_following"


# --- model asset record (§1, §3) ----------------------------------------------------------------------

@dataclass
class ModelAsset:
    """One versioned model asset (§1, §3).

    A marketing family name is NOT enough — we track the actual version,
    checksum, quantisation, and capability test results (§3).
    """
    asset_id: str                     # unique per version, not per family
    family: str                       # e.g. "qwen3", "llama3.2"
    version: str                      # specific version/weights identifier
    checksum: str = ""                # sha256 of the weights file
    quantisation: str = ""            # e.g. "q4_K_M", "q8_0", "f16"
    format: str = ""                  # e.g. "GGUF", "safetensors"
    size_gb: float = 0.0
    capabilities: list[ModelCapability] = field(default_factory=list)
    state: ModelAssetState = ModelAssetState.DISCOVERED
    license: str = ""
    source_url: str = ""
    local_path: str = ""
    capability_tests_passed: bool = False
    test_results: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_used_at: Optional[float] = None
    superseded_by: Optional[str] = None   # newer version that replaced this

    def verify_checksum(self) -> bool:
        """Verify the stored checksum matches a re-hash of the local file."""
        if not self.checksum or not self.local_path:
            return False
        try:
            h = hashlib.sha256()
            with open(self.local_path, "rb") as f:
                while chunk := f.read(1 << 20):
                    h.update(chunk)
            return h.hexdigest() == self.checksum
        except OSError:
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "family": self.family,
            "version": self.version,
            "checksum": self.checksum[:16] + "..." if self.checksum else "",
            "quantisation": self.quantisation,
            "format": self.format,
            "size_gb": self.size_gb,
            "capabilities": [c.value for c in self.capabilities],
            "state": self.state.value,
            "license": self.license,
            "capability_tests_passed": self.capability_tests_passed,
            "test_results": self.test_results,
            "superseded_by": self.superseded_by,
            "created_at": self.created_at,
        }


# --- model asset registry (§1, §3) ----------------------------------------------------------------------

class ModelAssetRegistry:
    """The versioned model asset registry (§1, §3).

    Every model is tracked by asset_id (family + version + quantisation),
    NOT by family name alone (§3: "a marketing model family name is not
    enough to identify the actual weights or service revision").
    """

    def __init__(self) -> None:
        self._assets: dict[str, ModelAsset] = {}
        self._family_versions: dict[str, list[str]] = {}

    def register(self, asset: ModelAsset) -> ModelAsset:
        """Register a model asset (§1)."""
        if asset.asset_id in self._assets:
            raise ValueError(f"duplicate asset_id: {asset.asset_id}")
        self._assets[asset.asset_id] = asset
        self._family_versions.setdefault(asset.family, []).append(asset.asset_id)
        return asset

    def get(self, asset_id: str) -> Optional[ModelAsset]:
        return self._assets.get(asset_id)

    def family_versions(self, family: str) -> list[ModelAsset]:
        """All registered versions of a model family (§3)."""
        return [self._assets[aid]
                for aid in self._family_versions.get(family, [])
                if aid in self._assets]

    def active_version(self, family: str) -> Optional[ModelAsset]:
        """The currently-serving version of a family (§3)."""
        for asset in reversed(self.family_versions(family)):
            if asset.state == ModelAssetState.SERVING:
                return asset
        return None

    def supersede(self, family: str, old_asset_id: str,
                  new_asset_id: str) -> bool:
        """§3: supersede a version. The old version is DEPRECATED, not deleted."""
        old = self._assets.get(old_asset_id)
        new = self._assets.get(new_asset_id)
        if not old or not new:
            return False
        if old.family != new.family:
            return False
        old.state = ModelAssetState.DEPRECATED
        old.superseded_by = new_asset_id
        return True

    def by_capability(self, capability: ModelCapability) -> list[ModelAsset]:
        """Find hosted+tested models with a capability (§1)."""
        return [a for a in self._assets.values()
                if capability in a.capabilities
                and a.state in (ModelAssetState.HOSTED, ModelAssetState.SERVING)
                and a.capability_tests_passed]

    def run_capability_tests(self, asset_id: str,
                              results: dict[str, Any]) -> bool:
        """§1: run and record capability tests for a model."""
        asset = self._assets.get(asset_id)
        if not asset:
            return False
        asset.state = ModelAssetState.TESTING
        asset.test_results = results
        asset.capability_tests_passed = all(
            v.get("passed", False) for v in results.values() if isinstance(v, dict))
        if asset.capability_tests_passed:
            asset.state = ModelAssetState.HOSTED
        else:
            asset.state = ModelAssetState.QUARANTINED
        return asset.capability_tests_passed

    def summary(self) -> dict[str, Any]:
        """Honest summary of the registry."""
        by_state = {}
        for a in self._assets.values():
            by_state[a.state.value] = by_state.get(a.state.value, 0) + 1
        return {
            "total_assets": len(self._assets),
            "families": sorted(self._family_versions.keys()),
            "by_state": by_state,
            "quarantined": [a.asset_id for a in self._assets.values()
                            if a.state == ModelAssetState.QUARANTINED],
        }


# --- fine-tuning gate (§2) ---------------------------------------------------------------------------

class FineTuningGate:
    """§2: fine-tuning/evaluation tracks only where compute, model licence,
    data consent, and quality gates permit.
    """

    def __init__(self) -> None:
        self._permitted: dict[str, bool] = {}

    def check_permitted(self, model_license: str, data_consent: bool,
                         compute_available: bool,
                         quality_gate: bool) -> dict[str, Any]:
        """Check if fine-tuning is permitted for a model (§2)."""
        reasons = []
        if "permissive" not in model_license.lower() and \
                "mit" not in model_license.lower() and \
                "apache" not in model_license.lower():
            reasons.append(f"model licence '{model_license}' may not permit derivatives")
        if not data_consent:
            reasons.append("data consent not obtained")
        if not compute_available:
            reasons.append("insufficient compute")
        if not quality_gate:
            reasons.append("quality gate not passed")

        permitted = len(reasons) == 0
        return {
            "permitted": permitted,
            "reasons": reasons,
            "note": "§2: not a prerequisite for the first free-cloud gateway milestone",
        }
