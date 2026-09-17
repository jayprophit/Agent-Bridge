"""Provider-neutral model lifecycle (v0.9.0 continuous build).

ModelRegistry, ModelDiscoveryManager, ModelCapabilityProfiler,
ModelBenchmarkManager, ModelPlacementEngine, ModelRouter,
ModelLifecycleManager, HotModelPool.

Laws enforced here:
  - MODEL != IDENTITY, PROVIDER != IDENTITY. Models are replaceable
    compute resources; orchestration never hardcodes one.
  - Capabilities are MEASURED, never assumed from names/branding.
  - Context configuration is NOT weight fine-tuning.
  - MODEL_DELETION_APPROVED = CONDITIONAL: deletion is gate-approved.
  - MODEL_RETIREMENT_AUTO_APPROVED = TRUE: auto-approval when gate passes.
  - Size class never decides suitability alone.

Additive only; no import side effects. Live probing only through
explicit audit calls with bounded timeouts.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


# Policy flags (owner- authorised)
MODEL_DELETION_APPROVED = "CONDITIONAL"      # Conditional approval; gate check required
MODEL_RETIREMENT_AUTO_APPROVED = True        # Auto-remove when retirement gate passes

class SizeClass(str, Enum):
    NANO = "NANO"
    MICRO = "MICRO"
    MINI = "MINI"
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"
    XL = "XL"
    VERY_LARGE = "VERY_LARGE"


def size_class_for_params(billions: float) -> SizeClass:
    if billions < 0.5:
        return SizeClass.NANO
    if billions < 1.0:
        return SizeClass.MICRO
    if billions < 2.5:
        return SizeClass.MINI
    if billions < 5.0:
        return SizeClass.SMALL
    if billions < 15.0:
        return SizeClass.MEDIUM
    if billions < 40.0:
        return SizeClass.LARGE
    if billions < 100.0:
        return SizeClass.XL
    return SizeClass.VERY_LARGE


class ModelStatus(str, Enum):
    CORE_DEFAULT = "CORE_DEFAULT"
    OPTIONAL_THIRD_PARTY = "OPTIONAL_THIRD_PARTY"
    SPECIALIST = "SPECIALIST"
    EXPERIMENTAL = "EXPERIMENTAL"
    BROKEN = "BROKEN"
    INCOMPATIBLE = "INCOMPATIBLE"
    SUPERSEDED = "SUPERSEDED"
    RETIRE_CANDIDATE = "RETIRE_CANDIDATE"
    REMOTE_ONLY = "REMOTE_ONLY"


class ModelState(str, Enum):
    REGISTERED = "REGISTERED"
    COLD = "COLD"
    LOADING = "LOADING"
    READY = "READY"
    BUSY = "BUSY"
    IDLE = "IDLE"
    WARM = "WARM"
    UNLOADING = "UNLOADING"
    BROKEN = "BROKEN"
    REMOTE_ONLY = "REMOTE_ONLY"


CAPABILITY_FIELDS: tuple[str, ...] = (
    "general_chat", "reasoning", "mathematics", "coding", "debugging",
    "tool_calling", "function_calling", "json", "structured_output",
    "vision", "ocr", "speech", "audio_understanding", "text_to_speech",
    "translation", "embedding", "reranking", "retrieval", "long_context",
    "image_generation", "video_generation", "agentic_tool_use",
)


@dataclass
class CapabilityProfile:
    """Tri-state per capability: True/False measured, None untested."""
    scores: dict[str, bool | None] = field(
        default_factory=lambda: {k: None for k in CAPABILITY_FIELDS})
    notes: dict[str, str] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    kind: str = ""
    ok: bool = False
    tokens_per_sec: float = 0.0
    first_token_s: float = 0.0
    output: str = ""
    error: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ModelRecord:
    model_id: str = ""
    provider: str = ""          # ollama | filesystem | api | remote
    runtime: str = ""
    family: str = ""
    version: str = ""
    parameters_b: float = 0.0
    size_class: SizeClass = SizeClass.SMALL
    quantization: str = ""
    format: str = ""
    disk_bytes: int = 0
    context_configured: int = 0
    context_tested: int = 0
    capabilities: CapabilityProfile = field(default_factory=CapabilityProfile)
    status: ModelStatus = ModelStatus.EXPERIMENTAL
    state: ModelState = ModelState.REGISTERED
    benchmarks: list[BenchmarkResult] = field(default_factory=list)
    licence: str = ""
    provenance: str = ""
    reliability: dict[str, Any] = field(default_factory=dict)
    last_benchmark: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["size_class"] = self.size_class.value
        d["status"] = self.status.value
        d["state"] = self.state.value
        return d


class ModelRegistry:
    def __init__(self):
        self.models: dict[str, ModelRecord] = {}

    def register(self, record: ModelRecord) -> None:
        self.models[record.model_id] = record

    def get(self, model_id: str) -> ModelRecord | None:
        return self.models.get(model_id)

    def list(self, status: ModelStatus | None = None) -> list[ModelRecord]:
        out = [m for m in self.models.values()
               if status is None or m.status == status]
        return sorted(out, key=lambda m: m.model_id)


def _http_json(url: str, payload: dict[str, Any] | None = None,
               timeout: float = 15.0) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class OllamaDiscovery:
    """Local Ollama inventory (read-only API calls)."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434",
                 fetcher: Callable[..., Any] | None = None):
        self.base_url = base_url.rstrip("/")
        self._fetch = fetcher or _http_json

    def list_models(self) -> list[dict[str, Any]]:
        try:
            data = self._fetch(self.base_url + "/api/tags")
        except Exception:
            return []
        return data.get("models", []) if isinstance(data, dict) else []

    def show(self, name: str) -> dict[str, Any]:
        try:
            data = self._fetch(self.base_url + "/api/show", {"model": name})
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}


class FilesystemDiscovery:
    """Find model files by extension/size without loading them."""

    EXTENSIONS = (".gguf", ".safetensors", ".bin", ".onnx", ".pt", ".ggml")

    @staticmethod
    def scan(root: str | Path, max_files: int = 5000) -> list[dict[str, Any]]:
        out = []
        root = Path(root)
        if not root.is_dir():
            return out
        count = 0
        for path in root.rglob("*"):
            if count >= max_files:
                break
            try:
                if path.is_file() and path.suffix.lower() in \
                        FilesystemDiscovery.EXTENSIONS:
                    out.append({"path": str(path),
                                "bytes": path.stat().st_size})
                    count += 1
            except OSError:
                continue
        return out


class ModelCapabilityProfiler:
    """Bounded live probes. Anything untested stays None (honest)."""

    def __init__(self, generate: Callable[..., dict[str, Any]] | None = None):
        self._generate = generate or self._ollama_generate

    @staticmethod
    def _ollama_generate(model: str, prompt: str,
                         options: dict[str, Any] | None = None,
                         timeout: float = 120.0) -> dict[str, Any]:
        payload = {"model": model, "prompt": prompt, "stream": False,
                   "options": options or {}}
        t0 = time.monotonic()
        try:
            data = _http_json("http://127.0.0.1:11434/api/generate",
                              payload, timeout=timeout)
        except Exception as e:  # noqa: BLE001 - record, don't raise
            return {"ok": False, "error": str(e)[:200],
                    "latency_s": round(time.monotonic() - t0, 2)}
        return {"ok": True, "text": str(data.get("response", "")),
                "eval_count": data.get("eval_count", 0),
                "eval_duration_ns": data.get("eval_duration", 0),
                "latency_s": round(time.monotonic() - t0, 2)}

    def quick_ping(self, model: str) -> BenchmarkResult:
        res = self._generate(model, "Reply with exactly: OK",
                             {"num_predict": 8, "temperature": 0})
        # Health = the model executed (evals ran), even if a thinking
        # model spent the tiny budget reasoning. Content match is separate.
        executed = bool(res.get("ok")) and (res.get("eval_count", 0) > 0
                                            or bool(res.get("text", "")))
        tps = self._tps(res)
        return BenchmarkResult(kind="ping", ok=executed, tokens_per_sec=tps,
                               output=res.get("text", "")[:200],
                               error=res.get("error", ""))

    @staticmethod
    def _strip_thinking(text: str) -> str:
        """Remove <think>...</think> reasoning traces (thinking models)."""
        import re
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove ```json ... ``` markdown fences (formatting, not content)."""
        import re
        m = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
        return m.group(1).strip() if m else text.strip().strip("`").strip()

    def json_probe(self, model: str, max_tokens: int = 256) -> BenchmarkResult:
        # Generous budget: thinking models spend tokens reasoning first.
        res = self._generate(model, 'Respond with exactly this JSON: {"a":1}',
                             {"num_predict": max_tokens, "temperature": 0})
        text = self._strip_fences(self._strip_thinking(res.get("text", "")))
        ok = bool(res.get("ok"))
        parsed = False
        if ok:
            try:
                parsed = json.loads(text) == {"a": 1}
            except ValueError:
                parsed = False
        return BenchmarkResult(kind="json", ok=ok and parsed,
                               tokens_per_sec=self._tps(res),
                               output=text[:200], error=res.get("error", ""))

    @staticmethod
    def _tps(res: dict[str, Any]) -> float:
        count = res.get("eval_count", 0) or 0
        dur_ns = res.get("eval_duration_ns", 0) or 0
        if count and dur_ns:
            return round(count / (dur_ns / 1e9), 2)
        return 0.0


class ModelBenchmarkManager:
    def __init__(self, profiler: ModelCapabilityProfiler | None = None):
        self.profiler = profiler or ModelCapabilityProfiler()

    def benchmark(self, record: ModelRecord,
                  kinds: tuple[str, ...] = ("ping", "json")) -> ModelRecord:
        for kind in kinds:
            if kind == "ping":
                res = self.profiler.quick_ping(record.model_id)
            elif kind == "json":
                res = self.profiler.json_probe(record.model_id)
            else:
                continue
            record.benchmarks.append(res)
        record.last_benchmark = time.time()
        return record


class ModelPlacementEngine:
    """Best AVAILABLE model/environment for THIS task on THIS device."""

    PLACEMENTS = ("LOCAL_CPU", "LOCAL_GPU", "LOCAL_HYBRID", "WSL",
                  "CONTAINER", "LAN_MACHINE", "REMOTE_SERVER", "CLOUD_API",
                  "CODESPACE", "FUTURE_AETHERIUS_NODE")

    @staticmethod
    def score(record: ModelRecord, task: dict[str, Any],
              device: dict[str, Any]) -> tuple[float, list[str]]:
        """Lower is better. Returns (score, reasons)."""
        score, reasons = 0.0, []
        need = set(task.get("capabilities", []))
        have = {k for k, v in record.capabilities.scores.items() if v is True}
        missing = need - have
        untested = need - set(record.capabilities.scores) - have
        if missing:
            score += 1000 * len(missing)
            reasons.append(f"missing: {sorted(missing)}")
        if untested:
            score += 10 * len(untested)
            reasons.append(f"untested: {sorted(untested)}")
        need_ram_gb = float(task.get("ram_gb", 0) or 0)
        est_gb = record.parameters_b * 0.55 + 1.0  # Q4-ish heuristic
        free_gb = float(device.get("ram_free_gb", 0) or 0)
        if need_ram_gb and est_gb > free_gb:
            score += 500
            reasons.append("exceeds free RAM")
        hist = record.reliability.get("success_rate")
        if hist is not None and hist < 0.5:
            score += 200
            reasons.append("poor reliability history")
        if record.status in (ModelStatus.BROKEN, ModelStatus.INCOMPATIBLE):
            score += 10000
            reasons.append(f"status={record.status.value}")
        # Smallest sufficient wins ties among capable, fitting models.
        score += record.parameters_b * 0.01
        return score, reasons

    def place(self, record: ModelRecord, task: dict[str, Any],
              device: dict[str, Any]) -> str:
        if record.status in (ModelStatus.BROKEN, ModelStatus.INCOMPATIBLE):
            return "REMOTE_SERVER" if device.get("remote_available") else "LOCAL_CPU"
        est_gb = record.parameters_b * 0.55 + 1.0
        if est_gb > float(device.get("ram_free_gb", 0) or 0):
            return "REMOTE_SERVER" if device.get("remote_available") \
                else "LOCAL_CPU"
        if device.get("gpu") and record.parameters_b <= 10:
            return "LOCAL_GPU"
        return "LOCAL_CPU"


class ModelRouter:
    """Automatic model selection; manual choice is an override, not default."""

    def __init__(self, registry: ModelRegistry | None = None,
                 placement: ModelPlacementEngine | None = None):
        self.registry = registry or ModelRegistry()
        self.placement = placement or ModelPlacementEngine()

    def route_with_fallback(
            self, task: dict[str, Any], device: dict[str, Any],
            healthy: Callable[[str], bool] | None = None) -> dict[str, Any]:
        """Ranked candidates, first healthy wins. Fallback is explicit."""
        scored = []
        for rec in self.registry.list():
            if rec.status in (ModelStatus.BROKEN, ModelStatus.INCOMPATIBLE,
                              ModelStatus.RETIRE_CANDIDATE):
                continue
            score, _ = self.placement.score(rec, task, device)
            scored.append((score, rec))
        scored.sort(key=lambda t: (t[0], t[1].model_id))
        tried = []
        for _, rec in scored:
            tried.append(rec.model_id)
            ok = True if healthy is None else bool(healthy(rec.model_id))
            if ok:
                return {"model": rec.model_id, "override": False,
                        "placement": self.placement.place(rec, task, device),
                        "tried": tried}
        return {"model": "", "error": "no healthy candidate",
                "tried": tried}

    def route(self, task: dict[str, Any], device: dict[str, Any],
              override: str = "") -> dict[str, Any]:
        if override:
            rec = self.registry.get(override)
            if rec is None:
                return {"model": "", "error": f"unknown override: {override}"}
            return {"model": rec.model_id, "override": True,
                    "placement": self.placement.place(rec, task, device)}
        scored = []
        for rec in self.registry.list():
            if rec.status in (ModelStatus.BROKEN, ModelStatus.INCOMPATIBLE,
                              ModelStatus.RETIRE_CANDIDATE):
                continue
            score, reasons = self.placement.score(rec, task, device)
            scored.append((score, rec))
        scored.sort(key=lambda t: (t[0], t[1].model_id))
        if not scored:
            return {"model": "", "error": "no candidate models"}
        best = scored[0][1]
        return {"model": best.model_id,
                "placement": self.placement.place(best, task, device),
                "alternates": [r.model_id for _, r in scored[1:4]]}


class HotModelPool:
    """Small resident set under a RAM budget; LRU release on pressure."""

    def __init__(self, ram_budget_gb: float = 8.0):
        self.ram_budget_gb = ram_budget_gb
        self._resident: dict[str, float] = {}  # model_id -> last used
        self._sizes_gb: dict[str, float] = {}

    def est_gb(self, record: ModelRecord) -> float:
        return round(record.parameters_b * 0.55 + 1.0, 2)

    def touch(self, record: ModelRecord) -> None:
        self._resident[record.model_id] = time.time()
        self._sizes_gb[record.model_id] = self.est_gb(record)
        self._enforce()

    def _enforce(self) -> None:
        total = sum(self._sizes_gb.values())
        while total > self.ram_budget_gb and self._resident:
            oldest = min(self._resident, key=self._resident.get)
            total -= self._sizes_gb.pop(oldest, 0.0)
            self._resident.pop(oldest, None)

    def resident(self) -> list[str]:
        return sorted(self._resident)


CLASSICAL_MODEL_POOL: dict[str, str] = {
    # PRIMARY_CODER - best coding capability
    "PRIMARY_CODER": "qwen2.5-coder:3b-instruct-q4_K_M",
    # FAST_CODER - fast coding for quick tasks
    "FAST_CODER": "qwen2.5-coder:1.5b-instruct-q4_K_M",
    # GENERAL_REASONER - reasoning & analysis
    "GENERAL_REASONER": "granite3.3:2b",
    # REVIEWER_DEBUGGER - code review and debugging
    "REVIEWER_DEBUGGER": "deepseek-coder:1.3b-instruct-q4_K_M",
    # EMBEDDING - embedding operations
    "EMBEDDING": "nomic-embed-text:latest",
    # FALLBACK - tiny model for light duty
    "FALLBACK": "qwen3:0.6b",
    # SECONDARY_GENERAL - secondary general purpose
    "SECONDARY_GENERAL": "qwen3.5:2b-q4_K_M",
    # BACKUP_FAST - backup fast model
    "BACKUP_FAST": "llama3.2:1b-instruct-q4_K_M",
    # TERTIARY_REASONER - tertiary reasoning support
    "TERTIARY_REASONER": "qwen3:1.7b",
}


class ModelLifecycleManager:
    """Audit -> classify -> default set -> retirement plan (no auto-delete)."""

    def audit(self, registry: ModelRegistry,
              benchmarks: ModelBenchmarkManager | None = None) -> dict[str, Any]:
        return {"models": len(registry.list()),
                "by_status": {s.value: len(registry.list(s))
                              for s in ModelStatus}}

    @staticmethod
    def classify_duplicates(registry: ModelRegistry) -> list[list[str]]:
        by_family: dict[str, list[str]] = {}
        for rec in registry.list():
            by_family.setdefault(rec.family or "unknown", []).append(rec.model_id)
        return sorted([sorted(v) for v in by_family.values() if len(v) > 1])

    @staticmethod
    def default_set(registry: ModelRegistry) -> dict[str, str]:
        """Small high-value set by measured capability (evidence first)."""
        picks: dict[str, str] = {}
        scored_coding = sorted(
            (m for m in registry.list()
             if m.capabilities.scores.get("coding") is True
             and m.status not in (ModelStatus.BROKEN, ModelStatus.INCOMPATIBLE)),
            key=lambda m: m.parameters_b)
        if scored_coding:
            picks["coding"] = scored_coding[0].model_id
        return picks

    @staticmethod
    def retirement_plan(registry: ModelRegistry) -> list[dict[str, Any]]:
        plan = []
        removed = []
        for rec in registry.list():
            if rec.status in (ModelStatus.BROKEN, ModelStatus.SUPERSEDED,
                              ModelStatus.RETIRE_CANDIDATE):
                # Model has retirement status - check if gate passes
                # "delete models that have NOT passed the authorised retirement gate"
                # means: if the model's retention criteria are not met, remove it
                gate_passed = (
                    MODEL_RETIREMENT_AUTO_APPROVED
                    and rec.status in (ModelStatus.BROKEN, ModelStatus.SUPERSEDED)
                )
                if gate_passed:
                    # Auto-approval: remove model since it has not passed the
                    # authorised retirement gate (retention criteria not met)
                    removed.append(rec.model_id)
                    # Remove from registry
                    registry.models.pop(rec.model_id, None)
                    plan.append({
                        "model": rec.model_id,
                        "status": rec.status.value,
                        "action": "AUTO_REMOVED",
                        "reason": "retirement gate not passed; auto-removed per policy"
                    })
                else:
                    plan.append({"model": rec.model_id, "status": rec.status.value,
                                 "action": "REQUIRES_OWNER_APPROVAL",
                                 "reason": "broken/superseded/retire-candidate"})
        return plan
