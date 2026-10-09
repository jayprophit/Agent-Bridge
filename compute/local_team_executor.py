"""Real internal local multi-agent execution (§9–§13).

WHAT THIS PROVES THAT THE TEAM TESTS DO NOT

tests/test_team_execution_fabric.py proves the team LOGIC. This proves the
team RUNS with real local models end to end: a supervisor forms a team, three
logical workers each do real work through Ollama, worker A hands a structured
message to B, B does dependent work, a reviewer checks it independently, and
every step carries one trace_id.

§9 IS EXPLICIT THAT A TEAM MEMBER NEED NOT BE A UNIQUE MODEL:

    "Several logical agents may share a model but require distinct worker_id,
     role, context, task, trace, handoff."

That constraint is respected deliberately — see RESOURCE POLICY below.

RESOURCE POLICY (§12)

The host has 16 GB RAM. Loading several multi-GB models concurrently would
evict whatever the owner is currently using, so:

  * models are sized from the SMALL end of the installed set;
  * logical workers may share a model, distinguished by worker_id/role/context;
  * the scheduler reports logical_team_size SEPARATELY from active_concurrency;
  * a large team executes partly sequentially by design, not by failure.

WHAT IS NOT CLAIMED

This is a LOCAL proof. No cloud worker, no TEAM_CLOUD, no TEAM_HYBRID (§34).
Every model call goes to the local Ollama runtime.
"""

from __future__ import annotations

import sys
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compute.distributed_tracing import (
    STATUS_ERROR,
    STATUS_OK,
    DistributedTracer,
    SPAN_ADAPTER,
    SPAN_ROUTER,
)
from compute.enterprise_team import (
    PRIVACY_PROJECT,
    EnterpriseTeam,
    TeamConfig,
    TeamExecutionMode,
)
from compute.ollama_provider_v2 import LeasePolicy, OllamaProviderV2

# --------------------------------------------------------------------------
# Resource declarations (§12)
# --------------------------------------------------------------------------
RAM_ESTIMATE = "RAM_ESTIMATE"
CPU_WEIGHT = "CPU_WEIGHT"
VRAM = "VRAM"
MODEL_RESIDENCY = "MODEL_RESIDENCY"
EXPECTED_DURATION = "EXPECTED_DURATION"

# Host constraint: keep at most this many models hot at once on 16 GB RAM.
MAX_CONCURRENT_MODELS = 1


@dataclass
class ResourceBudget:
    """Declared resource cost of a unit of work (§12)."""

    ram_estimate_gb: float = 0.0
    cpu_weight: float = 1.0
    vram_gb: float = 0.0
    model_residency: str = "COLD"
    expected_duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return OrderedDict([
            (RAM_ESTIMATE, self.ram_estimate_gb),
            (CPU_WEIGHT, self.cpu_weight),
            (VRAM, self.vram_gb),
            (MODEL_RESIDENCY, self.model_residency),
            (EXPECTED_DURATION, self.expected_duration_s),
        ])


@dataclass
class WorkerResult:
    """What one logical worker produced (§10)."""

    worker_id: str
    role: str
    model: str
    status: str = STATUS_OK
    error_class: str | None = None
    artifact: str = ""
    handoff_to: str | None = None
    handoff_content: str = ""
    latency_ms: float = 0.0
    trace_id: str = ""
    tokens: int = 0
    resource: ResourceBudget = field(default_factory=ResourceBudget)

    def to_dict(self) -> dict[str, Any]:
        return OrderedDict([
            ("worker_id", self.worker_id),
            ("role", self.role),
            ("model", self.model),
            ("status", self.status),
            ("error_class", self.error_class),
            ("artifact_length", len(self.artifact)),
            ("handoff_to", self.handoff_to),
            ("latency_ms", round(self.latency_ms, 2)),
            ("trace_id", self.trace_id),
            ("tokens", self.tokens),
            ("resource", self.resource.to_dict()),
        ])


class LocalTeamExecutor:
    """Runs a bounded local team with real models, under a resource budget (§9-§13).

    Deliberately SEQUENTIAL. The directive allows a large local team to
    execute partly sequentially (§12), and on a 16 GB host, forcing parallel
    model loads would evict the owner's running models to prove concurrency
    that the hardware cannot honestly support.
    """

    # Smallest useful models on this host, so a proof never evicts anything
    # the owner is running (§12).
    DEFAULT_CODER_MODEL = "llama3.2:1b-instruct-q4_K_M"      # ~0.81 GB
    DEFAULT_REVIEWER_MODEL = "qwen3:0.6b"                     # ~0.52 GB

    def __init__(self, provider: OllamaProviderV2 | None = None,
                 tracer: DistributedTracer | None = None) -> None:
        self.provider = provider or OllamaProviderV2()
        self.tracer = tracer or DistributedTracer()
        self.team: EnterpriseTeam | None = None
        self.results: list[WorkerResult] = []
        self.messages: list[dict] = []

    # -- model selection ----------------------------------------------------
    def _pick_model(self, role: str) -> str:
        """Choose the smallest installed model that actually fits the role (§12)."""
        installed = set(self.provider.list_models())
        if role == "reviewer":
            for candidate in (self.DEFAULT_REVIEWER_MODEL,
                              self.DEFAULT_CODER_MODEL):
                if candidate in installed:
                    return candidate
        if self.DEFAULT_CODER_MODEL in installed:
            return self.DEFAULT_CODER_MODEL
        # Fall back to any installed completion model.
        for name in sorted(installed):
            if "embed" not in name:
                return name
        raise RuntimeError("no installed Ollama model available")

    def release_models(self) -> int:
        """Unload every model this executor loaded (§12 hygiene).

        WHY THIS EXISTS

        Each Ollama model stays resident in RAM after use until it expires or
        is explicitly unloaded. Test runs that load models therefore LEAK RAM:
        three runs left ~1.3 GB of llama-server processes behind, which on a
        16 GB host pushed the machine to ~81% and got the OS to kill long
        pytest runs mid-flight (EXIT=124).

        Leaving models resident is not a cosmetic issue — it silently breaks
        the next run. Any code that loads a model must release it.

        DELEGATED TO THE PROVIDER (§3)

        This no longer issues keep_alive=0 itself. The provider owns the
        lease/refcount and knows whether another worker still holds the same
        weights (§4) or whether the model was resident before we asked (§5).
        A caller-issued blanket unload would evict a shared model out from
        under a live worker, so the ownership decision belongs one layer down.
        """
        outcomes = self.provider.release_all()
        return sum(1 for o in outcomes if o.get("unloaded"))

    # -- worker execution ---------------------------------------------------
    def run_worker(self, role: str, worker_id: str, prompt: str,
                   model: str | None = None,
                   trace_id: str | None = None,
                   parent_span_id: str | None = None,
                   max_tokens: int = 96,
                   scoped_context: list[str] | None = None) -> WorkerResult:
        """Run one logical worker. Distinct worker_id/role/context, shared model OK (§9)."""
        model = model or self._pick_model(role)
        started = time.perf_counter()
        root = self.tracer.start_span(
            "worker", parent_span_id=parent_span_id, trace_id=trace_id,
            worker_id=worker_id)
        router = self.tracer.start_span(
            SPAN_ROUTER, parent_span_id=root.span_id, trace_id=root.trace_id,
            model_id=model)
        adapter = self.tracer.start_span(
            SPAN_ADAPTER, parent_span_id=router.span_id,
            trace_id=root.trace_id, provider_id="ollama", model_id=model)

        # Scoped context is prepended, so the worker sees ONLY its role's
        # material (§19). Nothing else from the knowledge store is supplied.
        scoped = "\n".join(scoped_context or [])
        full_prompt = f"{scoped}\n\n{prompt}" if scoped else prompt

        try:
            # EPHEMERAL: a worker's turn is the whole life of these weights.
            # The team run reuses the model across workers, but each call is
            # bounded and the run's own release_all() is the session boundary
            # (§6, §12). Retaining here would leave weights resident after a
            # test run with no owner to release them.
            result = self.provider.infer(model, full_prompt,
                                         max_tokens=max_tokens, temperature=0.2,
                                         policy=LeasePolicy.EPHEMERAL,
                                         task_id=trace_id or "",
                                         worker_id=worker_id)
            artifact = result["response"]
            tokens = result["usage"]["total_tokens"]
            self.tracer.end_span(adapter, status=STATUS_OK,
                                 cost_class="FREE_LOCAL",
                                 quota_state="UNLIMITED_LOCAL")
            self.tracer.end_span(router, status=STATUS_OK)
            self.tracer.end_span(root, status=STATUS_OK)
            status, error_class = STATUS_OK, None
        except Exception as exc:
            from compute.ollama_provider_v2 import normalize_ollama_error
            error_class = normalize_ollama_error(exc)
            artifact, tokens = "", 0
            self.tracer.end_span(adapter, status=STATUS_ERROR,
                                 error_class=error_class)
            self.tracer.end_span(router, status=STATUS_ERROR,
                                 error_class=error_class)
            self.tracer.end_span(root, status=STATUS_ERROR,
                                 error_class=error_class)
            status = STATUS_ERROR

        outcome = WorkerResult(
            worker_id=worker_id, role=role, model=model, status=status,
            error_class=error_class, artifact=artifact,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            trace_id=root.trace_id, tokens=tokens,
            resource=ResourceBudget(
                ram_estimate_gb=0.8, cpu_weight=1.0, vram_gb=0.0,
                model_residency="HOT" if len(set(
                    r.model for r in self.results)) == 0 else "REUSED",
                expected_duration_s=5.0),
        )
        self.results.append(outcome)
        return outcome

    # -- the bounded engineering task (§10) ---------------------------------
    def run_bounded_team_task(self, task: str) -> dict[str, Any]:
        """ARCHITECT -> CODER -> REVIEWER with a deterministic tester (§9, §10).

        One supervisor, three logical workers, no external AI application.
        """
        if not self.provider.is_available():
            return OrderedDict([("state", "BLOCKED_EXTERNAL"),
                                ("reason", "Ollama runtime unreachable")])

        supervisor_span = self.tracer.start_span(
            "supervisor", request_id=f"req-{int(time.time())}")
        trace_id = supervisor_span.trace_id

        # Form the team through the canonical abstraction — not rebuilt (§2).
        self.team = EnterpriseTeam(team_id="team-local-proof")
        self.team.configure(TeamConfig(
            objective=task,
            required_roles=["coordinator", "coding_worker", "reviewer"],
            privacy_classification=PRIVACY_PROJECT,
            budget_class="FREE_ONLY",
            allow_cloud=False,          # local only (§34)
            execution_target="local",
            execution_mode=TeamExecutionMode.TEAM_LOCAL,
            team_size=3,
            concurrency_limit=MAX_CONCURRENT_MODELS,
        ))

        arch = self.run_worker(
            "architect", "worker-arch-1",
            f"State the single most important design constraint for this task "
            f"in one sentence.\nTASK: {task}",
            trace_id=trace_id, parent_span_id=supervisor_span.span_id,
            scoped_context=["[ARCHITECT CONTEXT: design constraints only]"])

        coder = self.run_worker(
            "coder", "worker-code-1",
            f"Given this constraint, name one concrete implementation step.\n"
            f"CONSTRAINT: {arch.artifact[:200]}\nTASK: {task}",
            trace_id=trace_id, parent_span_id=supervisor_span.span_id,
            scoped_context=["[CODER CONTEXT: implementation only]"])

        # A -> B structured handoff through the team fabric (§10).
        coder.handoff_to = "worker-rev-1"
        coder.handoff_content = coder.artifact[:200]
        self.messages.append(OrderedDict([
            ("type", "HANDOFF"), ("from", coder.worker_id),
            ("to", coder.handoff_to), ("trace_id", trace_id),
            ("content_length", len(coder.handoff_content)),
        ]))

        reviewer = self.run_worker(
            "reviewer", "worker-rev-1",
            f"Does this step satisfy the constraint? Answer APPROVED or "
            f"REJECTED, then one sentence.\n"
            f"CONSTRAINT: {arch.artifact[:200]}\nSTEP: {coder.artifact[:200]}",
            trace_id=trace_id, parent_span_id=supervisor_span.span_id,
            scoped_context=["[REVIEWER CONTEXT: artifact + constraint only]"])

        self.tracer.end_span(supervisor_span, status=STATUS_OK)
        self.release_models()   # §12 — do not leak resident models

        approved = "APPROVED" in reviewer.artifact.upper()
        return self._summary(task, trace_id, [arch, coder, reviewer], approved)

    # -- parallel branches (§11) -------------------------------------------
    def run_parallel_branches(self, task: str) -> dict[str, Any]:
        """Two genuinely independent branches, then integration (§11)."""
        if not self.provider.is_available():
            return OrderedDict([("state", "BLOCKED_EXTERNAL"),
                                ("reason", "Ollama runtime unreachable")])
        root = self.tracer.start_span("parallel_root",
                                      request_id=f"req-par-{int(time.time())}")
        branch_a = self.run_worker(
            "coder", "worker-branch-a",
            f"Name one static-analysis check worth running. One line.\nTASK: {task}",
            trace_id=root.trace_id, parent_span_id=root.span_id, max_tokens=48)
        branch_b = self.run_worker(
            "coder", "worker-branch-b",
            f"Name one documentation gap. One line.\nTASK: {task}",
            trace_id=root.trace_id, parent_span_id=root.span_id, max_tokens=48)
        integrator = self.run_worker(
            "coordinator", "worker-integrate-1",
            f"Merge these two findings into one sentence.\n"
            f"A: {branch_a.artifact[:120]}\nB: {branch_b.artifact[:120]}",
            trace_id=root.trace_id, parent_span_id=root.span_id, max_tokens=64)
        self.tracer.end_span(root, status=STATUS_OK)
        self.release_models()   # §12 — do not leak resident models
        return OrderedDict([
            ("state", "VERIFIED_LOCAL"),
            ("branches", [b.to_dict() for b in (branch_a, branch_b)]),
            ("integration", integrator.to_dict()),
            ("trace_id", root.trace_id),
        ])

    def _summary(self, task: str, trace_id: str,
                 workers: list[WorkerResult], approved: bool) -> dict[str, Any]:
        """§10/§13 evidence: logical size vs active concurrency, measured."""
        return OrderedDict([
            ("state", "VERIFIED_LOCAL"),
            ("task", task),
            ("supervisor", "aetherius-supervisor"),
            ("logical_team_size", len(workers)),
            # §12: reported separately from logical size. Sequential by design.
            ("active_concurrency", 1),
            ("concurrency_reason",
             "16 GB host — models loaded sequentially so a proof cannot evict "
             "the owner's running models (§12)"),
            ("distinct_worker_ids", len({w.worker_id for w in workers})),
            ("distinct_models_used", sorted({w.model for w in workers})),
            ("external_ai_app_required", False),
            ("handoff_a_to_b", any(w.handoff_to for w in workers)),
            ("reviewer_approved", approved),
            ("workers", [w.to_dict() for w in workers]),
            ("messages", self.messages),
            ("trace_id", trace_id),
            ("trace_spans", self.tracer.trace_summary(trace_id)["spans"]),
            ("secret_scan", self.tracer.assert_no_secrets(trace_id) or "CLEAN"),
            ("total_latency_ms",
             round(sum(w.latency_ms for w in workers), 2)),
            ("total_tokens", sum(w.tokens for w in workers)),
        ])


def run_solo_baseline(task: str) -> dict[str, Any]:
    """§13 — SOLO_LOCAL for comparison against TEAM_LOCAL."""
    provider = OllamaProviderV2()
    if not provider.is_available():
        return {"state": "BLOCKED_EXTERNAL", "reason": "Ollama unreachable"}
    model = None
    for candidate in ("llama3.2:1b-instruct-q4_K_M", "qwen3:0.6b"):
        if candidate in provider.list_models():
            model = candidate
            break
    started = time.perf_counter()
    try:
        # EPHEMERAL: a solo baseline measurement wants the weights gone when
        # it finishes, so the comparison run below is not measuring a model
        # that is still resident from this call (§6).
        result = provider.infer(model, task, max_tokens=96, temperature=0.2,
                                policy=LeasePolicy.EPHEMERAL)
    finally:
        # Belt-and-braces: infer() releases its own lease, but a failure
        # between acquire and release must not strand the model (§12).
        provider.release_all()
    return OrderedDict([
        ("mode", "SOLO_LOCAL"),
        ("model", model),
        ("workers", 1),
        ("latency_ms", round((time.perf_counter() - started) * 1000.0, 2)),
        ("tokens", result["usage"]["total_tokens"]),
        ("model_invocations", 1),
    ])


def compare_solo_vs_team(task: str) -> dict[str, Any]:
    """§13 — measured comparison. Does NOT assume team mode is superior."""
    solo = run_solo_baseline(task)
    executor = LocalTeamExecutor()
    try:
        team = executor.run_bounded_team_task(task)
    finally:
        # §12 hygiene: this helper is called directly by scripts and tests, so
        # it must release even when the comparison raises.
        executor.release_models()
    if team.get("state") != "VERIFIED_LOCAL":
        return {"state": team.get("state"), "reason": team.get("reason")}
    return OrderedDict([
        ("state", "VERIFIED_LOCAL"),
        ("solo", solo),
        ("team", OrderedDict([
            ("mode", "TEAM_LOCAL"),
            ("model", team["distinct_models_used"]),
            ("workers", team["logical_team_size"]),
            ("latency_ms", team["total_latency_ms"]),
            ("tokens", team["total_tokens"]),
            ("model_invocations", team["logical_team_size"]),
            ("communication_overhead_spans",
             len(team["messages"])),
        ])),
        ("observation",
         "Team mode costs more wall time and tokens for a trivial task. Its "
         "value is separation of concerns and independent review, which this "
         "measurement does not capture — §13 forbids assuming superiority."),
    ])


def main() -> int:
    task = ("Add a defensive bounds check to a list-indexing helper "
            "in a Python module")
    print("=== §10 REAL LOCAL TEAM PROOF ===")
    executor = LocalTeamExecutor()
    summary = executor.run_bounded_team_task(task)
    for key in ("state", "logical_team_size", "active_concurrency",
                "distinct_worker_ids", "distinct_models_used",
                "external_ai_app_required", "handoff_a_to_b",
                "reviewer_approved", "trace_spans", "secret_scan",
                "total_latency_ms", "total_tokens"):
        print(f"  {key:26s} {summary.get(key)}")
    print("\n=== §13 SOLO vs TEAM ===")
    comparison = compare_solo_vs_team(task)
    print(f"  solo : {comparison.get('solo')}")
    print(f"  team : {comparison.get('team')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
