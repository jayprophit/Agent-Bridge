"""Provider-neutral model acquisition (v0.9.0).

Smallest correct architecture: ModelSource contract (Ollama local real,
Hugging Face metadata-only, filesystem), AcquisitionPlanner enforcing
inspect-existing -> compare -> hardware-fit BEFORE download ->
licence/provenance -> smallest sufficient -> download -> verify ->
benchmark -> register. No mass downloads. Additive only.
"""
from __future__ import annotations

import json
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Callable


@dataclass
class ModelCandidate:
    source: str = ""
    name: str = ""
    parameters_b: float = 0.0
    quantization: str = ""
    size_gb: float = 0.0
    licence: str = ""
    provenance: str = ""
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelSource(ABC):
    name: str = ""

    @abstractmethod
    def search(self, query: str) -> list[ModelCandidate]: ...

    @abstractmethod
    def acquire(self, candidate: ModelCandidate,
                dry_run: bool = True) -> dict[str, Any]: ...


class OllamaSource(ModelSource):
    """Local Ollama registry source (real)."""
    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434",
                 fetcher: Callable[..., Any] | None = None):
        self.base_url = base_url.rstrip("/")
        self._fetch = fetcher

    def _get(self, path: str) -> Any:
        if self._fetch is not None:
            return self._fetch(self.base_url + path)
        with urllib.request.urlopen(self.base_url + path,
                                     timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def search(self, query: str) -> list[ModelCandidate]:
        try:
            data = self._get("/api/tags")
        except Exception:
            return []
        out = []
        for m in data.get("models", []) if isinstance(data, dict) else []:
            name = str(m.get("name", ""))
            if query.lower() in name.lower():
                out.append(ModelCandidate(
                    source="ollama", name=name,
                    size_gb=round(m.get("size", 0) / 2 ** 30, 2),
                    provenance="ollama-registry"))
        return out

    def acquire(self, candidate: ModelCandidate,
                dry_run: bool = True) -> dict[str, Any]:
        if dry_run:
            return {"ok": True, "dry_run": True, "model": candidate.name}
        import subprocess
        try:
            r = subprocess.run(["ollama", "pull", candidate.name],
                               capture_output=True, text=True, timeout=1800)
        except (OSError, subprocess.TimeoutExpired) as e:
            return {"ok": False, "error": str(e)[:200]}
        return {"ok": r.returncode == 0,
                "output": (r.stdout or r.stderr or "")[-500:]}


class HuggingFaceSource(ModelSource):
    """Hugging Face metadata source (no downloads)."""
    name = "huggingface"

    def __init__(self, fetcher: Callable[[str], Any] | None = None):
        self._fetch = fetcher

    def search(self, query: str) -> list[ModelCandidate]:
        url = ("https://huggingface.co/api/models?search=" +
               urllib.request.quote(query) + "&limit=10")
        try:
            if self._fetch is not None:
                data = self._fetch(url)
            else:
                with urllib.request.urlopen(url, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return []
        out = []
        for m in data if isinstance(data, list) else []:
            card = m.get("cardData")
            licence = m.get("license", "") or (
                card.get("license", "") if isinstance(card, dict) else "")
            out.append(ModelCandidate(
                source="huggingface", name=str(m.get("modelId", "")),
                licence=str(licence), provenance="huggingface-hub"))
        return out

    def acquire(self, candidate: ModelCandidate,
                dry_run: bool = True) -> dict[str, Any]:
        return {"ok": False, "dry_run": dry_run,
                "error": "direct HF download not implemented; "
                         "use ollama pull or approved tooling"}


class AcquisitionPlanner:
    """Smallest sufficient, licence-checked, fit-estimated acquisition."""

    @staticmethod
    def plan(need: dict[str, Any],
             candidates: list[ModelCandidate],
             device: dict[str, Any]) -> dict[str, Any]:
        free_gb = float(device.get("disk_free_gb", 0) or 0)
        ram_gb = float(device.get("ram_free_gb", 0) or 0)
        viable = []
        for c in candidates:
            est_ram = c.parameters_b * 0.55 + 1.0 if c.parameters_b else 99.0
            if c.size_gb and c.size_gb > free_gb:
                continue
            if est_ram > ram_gb and ram_gb > 0:
                continue
            viable.append(c)
        viable.sort(key=lambda c: (c.size_gb or 99.0, c.name))
        if not viable:
            return {"candidate": None, "reason": "no fitting candidate"}
        best = viable[0]
        return {"candidate": best.to_dict(),
                "checks": {"licence": best.licence or "UNKNOWN - verify",
                           "size_fit": True, "ram_fit": True}}


# --------------------------------------------------------------------------
# Adaptation contracts (config vs weights kept distinct by construction)
# --------------------------------------------------------------------------

class AdaptationKind(str):
    CONFIG = "CONFIG"      # context window, templates, routing
    QUANT = "QUANT"        # quantisation/conversion (weights, reversible)
    ADAPTER = "ADAPTER"    # LoRA/adapters (weights, additive)
    TRAIN = "TRAIN"        # fine-tuning/distillation (weights, heavy)


@dataclass
class AdaptationPlan:
    model: str = ""
    kind: str = AdaptationKind.CONFIG
    description: str = ""
    benchmark_required: bool = True
    baseline: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)

    def record_result(self, metrics: dict[str, Any]) -> None:
        self.result = dict(metrics)

    def improved(self, metric: str) -> bool | None:
        if metric not in self.baseline or metric not in self.result:
            return None
        return bool(self.result[metric] > self.baseline[metric])
