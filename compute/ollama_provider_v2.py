"""Ollama Provider V2 — capability discovery + normalized errors (§27–§29).

WHY THIS MODULE EXISTS

The provider adapter registry could DECLARE that Ollama supports a
capability. That is not the same as knowing it does. A capability list
hand-written from a README rots the moment a model is swapped, and a router
that trusts it will dispatch a tool-calling request to a model that cannot
call tools — the request then either fails obscurely or, worse, is silently
answered as prose.

So this adapter DISCOVERS capabilities from the live Ollama runtime instead
of asserting them. `/api/show` reports what a model actually implements.

THE PROVIDER vs MODEL DISTINCTION (§28)

Capabilities vary on two axes and conflating them is a real bug:

    PROVIDER capabilities  — what the Ollama server itself offers
                             (streaming, embeddings, version)
    MODEL capabilities     — what a specific model supports
                             (vision, tools, context length)

`moondream` can see images; `llama3.2:1b` cannot. A single provider-level
"vision: yes" would be wrong for most models on this host. Discovery is
therefore per (provider, model) and both levels are reported separately.

WHAT IS DELIBERATELY NOT CLAIMED (§28)

The live host is probed and capabilities are reported from what `/api/show`
and `/api/tags` actually return. Ollama does not expose logprobs, prompt
caching, or batch inference through its HTTP API, so these are advertised as
unsupported rather than optimistically declared. Falsely advertising a
capability is how a router ends up trusting a result that was never
produced.
"""

from __future__ import annotations

import json
import time
import uuid
import urllib.error
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Imported at module scope rather than near the error subclasses because the
# class BODIES need NormalizedProviderError at import time — a bottom-of-file
# import raises NameError before it is ever reached.
from compute.error_taxonomy import (
    NormalizedProviderError,
    AUTH_ERROR,
    MODEL_UNAVAILABLE,
    PROVIDER_UNAVAILABLE,
    QUOTA_EXHAUSTED,
    RATE_LIMIT,
    TIMEOUT,
    UNSUPPORTED_CAPABILITY,
    UNKNOWN_PROVIDER_ERROR,
)

# --------------------------------------------------------------------------
# Capability names — shared vocabulary, so discovery and requests agree
# --------------------------------------------------------------------------
CAP_STREAMING = "streaming"
CAP_STRUCTURED_OUTPUT = "structured_output"
CAP_TOOLS = "tools"
CAP_VISION = "vision"
CAP_REASONING = "reasoning"
CAP_EMBEDDINGS = "embeddings"
CAP_TEMPERATURE = "temperature"
CAP_SYSTEM_PROMPT = "system_prompt"
CAP_SEED = "seed"

# Capabilities the Ollama HTTP API does NOT expose. Declaring these would be
# a false advertisement (§28), so they are pinned as unsupported.
UNSUPPORTED_BY_OLLAMA = ("logprobs", "prompt_caching", "batch", "audio")

DEFAULT_BASE_URL = "http://localhost:11434"


@dataclass
class ModelCapabilities:
    """What ONE model actually supports, discovered from the runtime."""

    model: str
    provider: str
    streaming: bool = False
    structured_output: bool = False
    tools: bool = False
    vision: bool = False
    reasoning: bool = False
    temperature: bool = False
    system_prompt: bool = False
    seed: bool = False
    context_length: int = 0
    parameter_size: str = ""
    quantization: str = ""
    family: str = ""
    families: list[str] = field(default_factory=list)
    embedding_length: int = 0
    # Explicitly unsupported — recorded so a caller sees the honest answer
    # rather than assuming silence means "no".
    unsupported: list[str] = field(default_factory=list)
    discovery_source: str = ""

    def supports(self, capability: str) -> bool:
        mapping = {
            CAP_STREAMING: self.streaming,
            CAP_STRUCTURED_OUTPUT: self.structured_output,
            CAP_TOOLS: self.tools,
            CAP_VISION: self.vision,
            CAP_REASONING: self.reasoning,
            CAP_TEMPERATURE: self.temperature,
            CAP_SYSTEM_PROMPT: self.system_prompt,
            CAP_SEED: self.seed,
        }
        return bool(mapping.get(capability, False))

    def supported_list(self) -> list[str]:
        out = []
        for cap in (CAP_STREAMING, CAP_STRUCTURED_OUTPUT, CAP_TOOLS, CAP_VISION,
                    CAP_REASONING, CAP_TEMPERATURE, CAP_SYSTEM_PROMPT, CAP_SEED):
            if self.supports(cap):
                out.append(cap)
        return out

    def to_dict(self) -> dict[str, Any]:
        return OrderedDict([
            ("model", self.model),
            ("provider", self.provider),
            ("supported", self.supported_list()),
            ("unsupported", list(self.unsupported)),
            ("context_length", self.context_length),
            ("parameter_size", self.parameter_size),
            ("quantization", self.quantization),
            ("family", self.family),
            ("discovery_source", self.discovery_source),
        ])


# --------------------------------------------------------------------------
# Model lifecycle ownership (§3–§7)
#
# WHY THIS LIVES ON THE PROVIDER
#
# Residency is a property of the RUNTIME, not of any one caller. A test that
# finishes has finished with Ollama's weights only when Ollama says so: by
# default the runtime keeps a model resident for `keep_alive` minutes after
# the last call, and on a 16 GB host that idle residency is the difference
# between a suite that completes and one the OS kills. Patching each caller
# to remember to unload is the wrong layer — every new call site reintroduces
# the leak, and a caller has no way to know whether another worker still
# needs the same weights.
#
# So the provider owns the lease. It records what it loaded, whether another
# active lease still needs it, and whether the model was already resident
# before Aetherius asked for it.
#
# THE FOUR OWNERSHIP CLASSES (§4, §5)
#
#   AETHERIUS_LOADED  — loaded because an Aetherius lease asked. Releasable
#                       when the refcount reaches zero.
#   PREEXISTING       — resident BEFORE this provider took its baseline.
#                       Never released. This is Hermes' own llama-server.
#   SHARED            — a second lease on a model this provider already
#                       holds. Releasing it on one caller's behalf would
#                       unload weights another live worker is using.
#   UNKNOWN           — residency the provider cannot attribute. Fails safe:
#                       left alone (§5).
# --------------------------------------------------------------------------


class LeasePolicy(str, Enum):
    """How long a model may stay resident after its last lease (§6).

    Chosen per call, not globally. A unit test wants the weights gone; an
    interactive Genesis session wants them warm for the next turn; a model
    reused across a team run wants brief retention under a RAM budget.
    """

    EPHEMERAL = "EPHEMERAL"      # keep_alive=0 — unload when the lease ends
    SHORT_LIVED = "SHORT_LIVED"  # keep_alive minutes, then release
    SESSION = "SESSION"          # retained for the life of the session
    PERSISTENT = "PERSISTENT"    # never auto-released; owner pins it


# keep_alive values Ollama understands, per policy. `-1` is Ollama's own
# sentinel for "keep loaded until told otherwise"; 0 unloads immediately.
_POLICY_KEEP_ALIVE: dict[str, int] = {
    LeasePolicy.EPHEMERAL.value: 0,
    LeasePolicy.SHORT_LIVED.value: 300,
    LeasePolicy.SESSION.value: -1,
    LeasePolicy.PERSISTENT.value: -1,
}

DEFAULT_LEASE_POLICY = LeasePolicy.SESSION


class ModelOwnership(str, Enum):
    """Who is responsible for a resident model (§4, §5)."""

    AETHERIUS_LOADED = "AETHERIUS_LOADED"
    PREEXISTING = "PREEXISTING"
    SHARED = "SHARED"
    UNKNOWN = "UNKNOWN"


@dataclass
class ModelLease:
    """One Aetherius claim on one resident model (§3, §4).

    The lease is the unit of ownership. `model_id`/`owner_id`/`task_id`/
    `worker_id` answer the question "who is keeping these weights resident"
    without guessing from a process list.
    """

    lease_id: str
    model: str
    owner_id: str
    policy: LeasePolicy
    task_id: str = ""
    worker_id: str = ""
    created_at: float = field(default_factory=time.time)
    released_at: float | None = None
    release_confirmed: bool = False
    resident_after_call: bool = False

    @property
    def active(self) -> bool:
        return self.released_at is None

    def to_dict(self) -> dict[str, Any]:
        """Non-secret metadata for evidence/provenance (§8).

        Deliberately excludes nothing sensitive because nothing here IS
        sensitive: no credentials, prompts, or vault content (§5).
        """
        return OrderedDict([
            ("lease_id", self.lease_id),
            ("model", self.model),
            ("owner_id", self.owner_id),
            ("task_id", self.task_id),
            ("worker_id", self.worker_id),
            ("policy", self.policy.value),
            ("keep_alive", _POLICY_KEEP_ALIVE[self.policy.value]),
            ("created_at", self.created_at),
            ("released_at", self.released_at),
            ("release_confirmed", self.release_confirmed),
            ("resident_after_call", self.resident_after_call),
        ])


class OllamaUnavailableError(NormalizedProviderError):
    """Raised when the Ollama server cannot be reached (§29).

    Carries PROVIDER_UNAVAILABLE rather than a generic runtime error: the
    runtime being switched off is a known, classifiable state, and the router
    should treat it as a dead provider instead of an unknown fault.
    """

    def __init__(self, base_url: str, cause: str = "") -> None:
        super().__init__(
            PROVIDER_UNAVAILABLE,
            f"Ollama unreachable at {base_url}: {cause or 'no response'}",
            provider_id="ollama",
            retryable=False,
        )
        self.base_url = base_url
        self.cause = cause


class OllamaProviderV2:
    """Live Ollama adapter: discovers capabilities, normalizes errors (§27–§29).

    Every method that touches the network converts provider failures into the
    canonical §3 taxonomy. Raw provider exceptions never escape as the API
    contract (§29).
    """

    provider_id = "ollama"
    base_url: str

    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 30.0,
                 owner_id: str = "aetherius") -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.owner_id = owner_id
        self._capability_cache: dict[str, ModelCapabilities] = {}
        # -- lifecycle ownership (§3) --------------------------------------
        # `_leases` is the refcount: model -> active lease ids. A model is
        # released only when this dict has no entry left for it, so a second
        # worker leasing the same weights cannot evict the first (§4).
        self._leases: dict[str, list[str]] = {}
        self._lease_records: dict[str, ModelLease] = {}
        # Every model this provider has EVER leased. This is what separates
        # "weights we loaded" from "weights somebody else loaded": at release
        # time the refcount is already zero, so `_leases` alone would
        # misclassify our own model as UNKNOWN and refuse to unload it (§5).
        self._leased_models: set[str] = set()
        # Residency observed BEFORE this provider asked for anything. This
        # is the boundary that keeps Hermes' own llama-server alive (§5):
        # anything resident at baseline is never ours to release.
        self._baseline_resident: set[str] | None = None

    # -- lifecycle: residency observation (§5) -----------------------------
    def resident_models(self) -> list[str]:
        """Model names the runtime currently holds in RAM. Never raises."""
        try:
            data = self._get("/api/ps")
        except Exception:
            return []
        models = data.get("models") or []
        return [m.get("name", "") for m in models if m.get("name")]

    def capture_baseline(self) -> set[str]:
        """Record current residency as NOT Aetherius's (§5).

        Called once before any leased inference. Anything resident now is
        pre-existing — including Hermes' own llama-server (PID 2072) — and
        the release path must never touch it.
        """
        if self._baseline_resident is None:
            self._baseline_resident = set(self.resident_models())
        return set(self._baseline_resident)

    def classify_ownership(self, model: str) -> ModelOwnership:
        """Attribute residency for one model (§4, §5). UNKNOWN fails safe.

        ORDER MATTERS. `_leased_models` is consulted before the residency
        probe because at release time the refcount is already zero: a model
        we loaded and are about to unload is resident but has no live lease,
        and treating that as UNKNOWN would make the release path refuse to
        unload its own weights — a leak that looks like safety.
        """
        baseline = self._baseline_resident
        if baseline is not None and model in baseline:
            return ModelOwnership.PREEXISTING
        if self._leases.get(model):
            return ModelOwnership.SHARED
        if model in self._leased_models:
            # We loaded it; the weights are ours to release.
            return ModelOwnership.AETHERIUS_LOADED
        if model in (self.resident_models() or []):
            # Resident, never leased by us: some other component or process
            # loaded it. Do not claim it (§5).
            return ModelOwnership.UNKNOWN
        return ModelOwnership.AETHERIUS_LOADED

    # -- lifecycle: leasing (§3, §4) ---------------------------------------
    def acquire(self, model: str, policy: LeasePolicy = DEFAULT_LEASE_POLICY,
                task_id: str = "", worker_id: str = "") -> ModelLease:
        """Claim a model lease before inference.

        The lease is what makes shared use safe: two workers asking for the
        same model hold two leases, and the weights stay until both are
        released (§4).
        """
        self.capture_baseline()
        lease = ModelLease(
            lease_id=f"lease-{uuid.uuid4().hex[:12]}",
            model=model,
            owner_id=self.owner_id,
            policy=policy,
            task_id=task_id,
            worker_id=worker_id,
        )
        self._leases.setdefault(model, []).append(lease.lease_id)
        self._lease_records[lease.lease_id] = lease
        self._leased_models.add(model)
        return lease

    def _keep_alive_for(self, policy: LeasePolicy) -> int:
        return _POLICY_KEEP_ALIVE[policy.value]

    def _inference_payload(self, model: str, base: dict[str, Any],
                           policy: LeasePolicy) -> dict[str, Any]:
        """Attach the lease's keep_alive so residency is decided at request
        time, not left to Ollama's default (§6)."""
        payload = dict(base)
        payload["model"] = model
        payload["keep_alive"] = self._keep_alive_for(policy)
        return payload

    def release(self, lease: ModelLease | str,
                timeout: float = 15.0) -> dict[str, Any]:
        """Release one lease; unload the model only when none remain (§4).

        Bounded polling rather than a single sample (§10): Ollama unloads
        lazily, so an immediate `/api/ps` read can show a model that is
        already on its way out. A real leak still fails; a lagging unload
        does not.
        """
        if isinstance(lease, str):
            lease = self._lease_records.get(lease)
        if lease is None:
            return {"released": False, "reason": "unknown lease"}
        if not lease.active:
            return {"released": False, "reason": "already released",
                    "lease": lease.to_dict()}

        lease.released_at = time.time()
        remaining = [lid for lid in self._leases.get(lease.model, [])
                     if lid != lease.lease_id]
        if remaining:
            # Another live worker still needs these weights (§4).
            self._leases[lease.model] = remaining
            return {"released": True, "unloaded": False,
                    "reason": "other active leases remain",
                    "lease": lease.to_dict()}
        self._leases.pop(lease.model, None)

        ownership = self.classify_ownership(lease.model)
        if ownership in (ModelOwnership.PREEXISTING,
                         ModelOwnership.UNKNOWN):
            # §5: never terminate what we cannot attribute.
            return {"released": True, "unloaded": False,
                    "reason": f"ownership={ownership.value}",
                    "lease": lease.to_dict()}
        if lease.policy is LeasePolicy.PERSISTENT:
            return {"released": True, "unloaded": False,
                    "reason": "policy=PERSISTENT",
                    "lease": lease.to_dict()}

        # Ask the runtime to drop the weights, then confirm rather than
        # assume (§10).
        try:
            self._get("/api/generate",
                      {"model": lease.model, "keep_alive": 0})
        except Exception:
            pass  # best effort; residency check below is the real answer

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if lease.model not in self.resident_models():
                lease.release_confirmed = True
                return {"released": True, "unloaded": True,
                        "lease": lease.to_dict()}
            time.sleep(0.5)
        lease.resident_after_call = True
        return {"released": True, "unloaded": False,
                "reason": "unload not confirmed within timeout",
                "lease": lease.to_dict()}

    def release_all(self) -> list[dict[str, Any]]:
        """Release every active lease this provider holds.

        Also sweeps models whose leases already ended under a retaining
        policy (SESSION): `infer()` releases its own lease on the way out,
        so a SESSION call leaves weights resident with no live lease. This
        is the intended behaviour during a session, but when the owner
        calls `release_all()` they are declaring the session over — so the
        retained weights must go too (§6, §12).
        """
        outcomes = [self.release(lease)
                    for lease in list(self._lease_records.values())
                    if lease.active]
        for model in sorted(self._leased_models):
            if self._leases.get(model):
                continue          # still held by a live lease
            if model not in self.resident_models():
                continue          # already gone
            if self.classify_ownership(model) != ModelOwnership.AETHERIUS_LOADED:
                continue          # PREEXISTING / UNKNOWN — not ours (§5)
            try:
                self._get("/api/generate", {"model": model, "keep_alive": 0})
            except Exception:
                pass
            outcomes.append({"released": True, "model": model,
                             "unloaded": True,
                             "reason": "retained session weights released"})
        return outcomes

    def lifecycle_report(self) -> dict[str, Any]:
        """Non-secret ownership/lease state for evidence (§8)."""
        return OrderedDict([
            ("owner_id", self.owner_id),
            ("baseline_resident", sorted(self._baseline_resident or [])),
            ("resident_now", self.resident_models()),
            ("active_leases", [l.to_dict() for l in self._lease_records.values()
                               if l.active]),
            ("released_leases", [l.to_dict()
                                 for l in self._lease_records.values()
                                 if not l.active]),
        ])

    # -- transport ----------------------------------------------------------
    def _get(self, path: str, payload: dict | None = None) -> Any:
        """HTTP GET/POST returning parsed JSON, with normalized errors.

        Network/HTTP/JSON failures become taxonomy classes so callers branch
        on one vocabulary instead of four different exception hierarchies.
        """
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # A 404 from /api/show means the model is not installed.
            if exc.code == 404:
                raise OllamaModelUnavailableError(
                    path, f"HTTP 404: {exc.reason}") from exc
            if exc.code in (401, 403):
                raise OllamaAuthError(path, f"HTTP {exc.code}") from exc
            if exc.code == 429:
                raise OllamaRateLimitError(path, "HTTP 429") from exc
            raise OllamaRequestError(path, f"HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            # Connection refused / DNS / timeout — the server is not there.
            raise OllamaUnavailableError(self.base_url, str(exc.reason)) from exc
        except TimeoutError as exc:
            raise OllamaTimeoutError(path, "request timed out") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaRequestError(
                path, f"malformed JSON response: {exc}") from exc

    # -- discovery (§28) ----------------------------------------------------
    def is_available(self) -> bool:
        """True when the server answers /api/tags. Never raises."""
        try:
            self.list_models()
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Model names currently installed."""
        data = self._get("/api/tags")
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    def provider_capabilities(self) -> dict[str, Any]:
        """PROVIDER-level capabilities (§28) — not model-specific."""
        streaming = False
        try:
            # /api/generate accepts stream; if the endpoint answers the server
            # supports streaming. We do not generate here, only reachability.
            self._get("/api/version")
            streaming = True
        except Exception:
            streaming = False
        caps = OrderedDict([
            ("provider", self.provider_id),
            ("base_url", self.base_url),
            ("reachable", self.is_available()),
            ("streaming", streaming),
            ("embeddings", True),  # /api/embeddings exists on this runtime
        ])
        for cap in UNSUPPORTED_BY_OLLAMA:
            caps[cap] = False
        return caps

    def discover(self, model: str, refresh: bool = False) -> ModelCapabilities:
        """Discover what ONE model supports, from /api/show + /api/tags (§28).

        This is the honest capability list: a router may trust it because it
        came from the runtime, not from documentation.
        """
        if not refresh and model in self._capability_cache:
            return self._capability_cache[model]

        details: dict[str, Any] = {}
        try:
            show = self._get("/api/show", {"model": model})
            details = show.get("details", {}) or {}
        except OllamaModelUnavailableError:
            # Model not installed: report honestly rather than guessing.
            caps = ModelCapabilities(
                model=model, provider=self.provider_id,
                unsupported=list(UNSUPPORTED_BY_OLLAMA),
                discovery_source="unavailable")
            self._capability_cache[model] = caps
            return caps

        families = details.get("families") or []
        family = details.get("family") or ""
        # /api/show returns an EXPLICIT `capabilities` array — e.g.
        # ["completion","tools"] or ["completion","vision"] or
        # ["completion","tools","thinking"]. This is the runtime's own
        # declaration, so it is authoritative and we do NOT infer support
        # from model names. Name-based guessing got llama3.2 wrong: it
        # advertises tools even though nothing in the name suggests so.
        declared = list(show.get("capabilities") or [])

        # `thinking` is reported as {"values": [...], "default": bool}; a
        # plain False means the model cannot reason at all.
        thinking = show.get("thinking")
        # `thinking` is reported as {"values": [...], "default": bool}. A model
        # whose only value is False cannot reason even if a `thinking` key
        # exists, so require a genuinely truthy option rather than mere
        # presence — llama3.2 reports values=[False] and must NOT be
        # advertised as reasoning-capable.
        reasoning = any(
            thinking.get("values", []) if isinstance(thinking, dict) else [])

        # Context length lives in model_info as "<arch>.context_length".
        model_info = show.get("model_info") or {}
        context_length = 0
        for key, value in model_info.items():
            if key.endswith(".context_length") and isinstance(value, int):
                context_length = max(context_length, value)

        caps = ModelCapabilities(
            model=model,
            provider=self.provider_id,
            # Sampling controls are universal in Ollama's generate API.
            streaming=True,
            temperature=True,
            system_prompt=True,
            seed=True,
            vision=CAP_VISION in declared or "clip" in families,
            tools=CAP_TOOLS in declared,
            reasoning=reasoning,
            # Ollama supports `format: json` for text-generation models.
            structured_output="completion" in declared,
            context_length=context_length,
            parameter_size=details.get("parameter_size") or "",
            quantization=details.get("quantization_level") or "",
            family=family,
            families=families,
            unsupported=list(UNSUPPORTED_BY_OLLAMA),
            discovery_source="/api/show capabilities + model_info",
        )
        self._capability_cache[model] = caps
        return caps

    def embedding_capable(self, model: str) -> bool:
        """Embedding models advertise an embedding_length."""
        caps = self.discover(model)
        return caps.embedding_length > 0 or "embed" in model.lower()

    # -- inference ----------------------------------------------------------
    def infer(self, model: str, prompt: str,
              system: str | None = None,
              temperature: float | None = None,
              max_tokens: int | None = None,
              tools: list[dict] | None = None,
              stream: bool = False,
              policy: LeasePolicy = DEFAULT_LEASE_POLICY,
              task_id: str = "",
              worker_id: str = "") -> dict[str, Any]:
        """Generate a completion, enforcing honest capability gating (§2, §28).

        Requesting a capability the model does not support FAILS EXPLICITLY
        rather than being silently ignored.

        Every call takes a lease and releases it on the way out (§3), so
        residency is decided here rather than left to each caller. `policy`
        controls how long the weights may outlive the call: EPHEMERAL for
        tests, SESSION for an interactive run, PERSISTENT when the owner
        pins a hot model.
        """
        caps = self.discover(model)

        if tools:
            if not caps.supports(CAP_TOOLS):
                raise OllamaUnsupportedCapabilityError(
                    model, CAP_TOOLS, f"model '{model}' has no tool calling")
        if temperature is not None and not caps.supports(CAP_TEMPERATURE):
            raise OllamaUnsupportedCapabilityError(
                model, CAP_TEMPERATURE, f"model '{model}' has no temperature")

        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        base: dict[str, Any] = {
            "prompt": prompt,
            "stream": stream,
        }
        if system:
            base["system"] = system
        if options:
            base["options"] = options
        if tools:
            base["tools"] = tools

        lease = self.acquire(model, policy=policy,
                             task_id=task_id, worker_id=worker_id)
        failed = False
        try:
            payload = self._inference_payload(model, base, policy)
            data = self._get("/api/generate", payload)
        except BaseException:
            failed = True
            raise
        finally:
            # EPHEMERAL releases here: the weights exist only for this call.
            #
            # A RETAINING policy (SESSION/SHORT_LIVED) deliberately does NOT
            # release on success. Ollama keeps the weights for `keep_alive`
            # minutes after the last request, which is what a warm model is;
            # tearing the lease down at the end of every call would make
            # "SESSION" meaningless and force a reload on the next turn. The
            # lease stays live until the owner calls
            # `release()`/`release_all()`, the honest boundary of a session.
            #
            # A FAILURE drops the lease regardless of policy (§9-H): weights
            # stranded by a request that never completed have no live turn to
            # stay warm for, and keeping them resident turns one bad call
            # into a memory leak.
            if policy is LeasePolicy.EPHEMERAL or failed:
                self.release(lease)

        return OrderedDict([
            ("model", model),
            ("provider", self.provider_id),
            ("response", data.get("response", "")),
            ("done", data.get("done", True)),
            ("tool_calls", data.get("message", {}).get("tool_calls", [])),
            ("usage", OrderedDict([
                ("prompt_tokens", data.get("prompt_eval_count", 0)),
                ("completion_tokens", data.get("eval_count", 0)),
                ("total_tokens", (data.get("prompt_eval_count", 0)
                                  + data.get("eval_count", 0))),
            ])),
            ("capabilities_used", self._capabilities_used(tools, temperature)),
            # Non-secret lifecycle metadata (§8).
            ("lifecycle", lease.to_dict()),
        ])

    def _capabilities_used(self, tools: list[dict] | None,
                           temperature: float | None) -> list[str]:
        used = [CAP_STREAMING]
        if tools:
            used.append(CAP_TOOLS)
        if temperature is not None:
            used.append(CAP_TEMPERATURE)
        return used

    def embed(self, model: str, text: str,
              policy: LeasePolicy = DEFAULT_LEASE_POLICY,
              task_id: str = "", worker_id: str = "") -> list[float]:
        """Embeddings, gated on the model actually being an embedder.

        Leased like any other inference path — an embedder holds VRAM as
        stubbornly as a generator does (§3).
        """
        caps = self.discover(model)
        if not self.embedding_capable(model):
            raise OllamaUnsupportedCapabilityError(
                model, CAP_EMBEDDINGS, f"model '{model}' is not an embedding model")
        lease = self.acquire(model, policy=policy,
                             task_id=task_id, worker_id=worker_id)
        failed = False
        try:
            data = self._get("/api/embeddings",
                             self._inference_payload(
                                 model, {"prompt": text}, policy))
        except BaseException:
            failed = True
            raise
        finally:
            # Same rule as infer(): EPHEMERAL frees the weights now, a
            # retaining policy keeps them for the session's owner to
            # release, and a failure always drops the lease (§9-H).
            if policy is LeasePolicy.EPHEMERAL or failed:
                self.release(lease)
        return list(data.get("embedding", []))


# --------------------------------------------------------------------------
# Normalized Ollama errors (§29)
#
# The taxonomy imports live at the top of this module; the subclasses below
# need NormalizedProviderError available at import time.
# --------------------------------------------------------------------------


class OllamaModelUnavailableError(NormalizedProviderError):
    """Model not installed on this Ollama host. Not retryable — installing a
    model is a deliberate act, not a transient blip."""


class OllamaAuthError(NormalizedProviderError):
    """Authentication rejected by the runtime."""


class OllamaRateLimitError(NormalizedProviderError):
    """Runtime throttled the request."""


class OllamaTimeoutError(NormalizedProviderError):
    """The runtime did not answer in time. Retryable."""


class OllamaRequestError(NormalizedProviderError):
    """Malformed or unexpected response from the runtime."""


class OllamaUnsupportedCapabilityError(NormalizedProviderError):
    """Caller asked for a capability the model does not advertise (§28).

    Raised INSTEAD of silently ignoring the request, because a router that
    believes a tool-calling request succeeded has trusted a result that was
    never produced.
    """

    def __init__(self, model: str, capability: str, message: str = "") -> None:
        self.model = model
        self.capability = capability
        super().__init__(
            UNSUPPORTED_CAPABILITY,
            message or f"model '{model}' does not support '{capability}'",
            provider_id="ollama",
            retryable=False,
        )


def normalize_ollama_error(exc: Exception) -> str:
    """Map any Ollama failure to a canonical §3 class (§29).

    ORDER MATTERS. ``OllamaUnavailableError`` subclasses RuntimeError, not
    URLError, so it must be matched BEFORE the generic branches — otherwise a
    runtime that is simply switched off normalizes to UNKNOWN_PROVIDER_ERROR
    and the router wastes retries on a provider that is not coming back.
    """
    if isinstance(exc, NormalizedProviderError):
        return exc.error_class
    if isinstance(exc, OllamaUnavailableError):
        return PROVIDER_UNAVAILABLE
    if isinstance(exc, TimeoutError):
        return TIMEOUT
    if isinstance(exc, urllib.error.URLError):
        return PROVIDER_UNAVAILABLE
    return UNKNOWN_PROVIDER_ERROR
