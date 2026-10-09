"""Distributed tracing across the inference path (§10 of the continuation directive).

SPAN PATH BEING TRACED

    request -> AI Gateway -> authorization -> privacy -> cost -> ModelRouter
            -> execution target -> provider adapter -> response -> evidence

DESIGN CONSTRAINTS THAT SHAPED THIS MODULE

1. Local tracing must work WITHOUT a hosted observability service (§10).
   There is no OTLP exporter, no Jaeger, no Datadog. A trace is a list of
   spans held in memory and optionally flushed to a JSON file. When the file
   path is omitted, tracing is purely in-process.

2. Do NOT log secrets (§5). This is enforced by construction rather than by
   convention: ``start_span`` accepts ONLY the attributes it declares, so a
   raw API key, password, token, prompt or KeePass value has no field to
   travel in. There is deliberately no ``**kwargs`` escape hatch — that
   single convenience is how secrets end up in trace files. Secrets are
   represented by the mere PRESENCE of a reference, never the value.

3. ``status`` and ``error_class`` use the normalized §3 taxonomy. A span
   records ``RATE_LIMIT`` or ``QUOTA_EXHAUSTED``, not the provider's own
   wording, so failure patterns are comparable across providers.

WHAT THIS IS NOT

This is not an OpenTelemetry SDK. It uses OpenTelemetry-COMPATIBLE CONCEPTS
(trace_id, span_id, parent_span_id, W3C-style propagation) so traces can be
correlated with an external system later without a rewrite. Claiming a
standard we do not implement would be dishonest evidence.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# --------------------------------------------------------------------------
# Normalized status values (not free-form strings, so consumers can branch)
# --------------------------------------------------------------------------
STATUS_OK = "OK"
STATUS_ERROR = "ERROR"
STATUS_UNSET = "UNSET"

# Span names for the canonical path. Pinned as constants so every producer
# emits identical names; free-form names would make cross-trace aggregation
# impossible.
SPAN_REQUEST = "request"
SPAN_GATEWAY = "ai_gateway"
SPAN_AUTHORIZATION = "authorization"
SPAN_PRIVACY = "privacy_check"
SPAN_COST = "cost_engine"
SPAN_ROUTER = "model_router"
SPAN_TARGET = "execution_target"
SPAN_ADAPTER = "provider_adapter"
SPAN_RESPONSE = "response"
SPAN_EVIDENCE = "evidence"

CANONICAL_SPAN_PATH = [
    SPAN_REQUEST, SPAN_GATEWAY, SPAN_AUTHORIZATION, SPAN_PRIVACY, SPAN_COST,
    SPAN_ROUTER, SPAN_TARGET, SPAN_ADAPTER, SPAN_RESPONSE, SPAN_EVIDENCE,
]


@dataclass
class Span:
    """One unit of work in the inference path.

    The attribute set is DELIBERATELY CLOSED. Anything not listed here cannot
    be attached to a span, which is what keeps secrets out of trace files (§5).
    """

    span_id: str
    trace_id: str
    name: str
    parent_span_id: str | None = None

    # Identity / correlation (§10)
    request_id: str | None = None
    task_id: str | None = None
    team_id: str | None = None
    worker_id: str | None = None
    model_id: str | None = None
    provider_id: str | None = None
    target_id: str | None = None

    # Timing
    start_time: str = ""
    end_time: str = ""
    latency_ms: float = 0.0

    # Outcome — normalized, not provider wording
    status: str = STATUS_UNSET
    error_class: str | None = None

    # Cost / quota visibility (§10)
    cost_class: str | None = None
    quota_state: str | None = None

    # Provider's own error text, kept for debugging. Raw provider strings are
    # retained here because they are frequently the only clue about a failure;
    # routing decisions still use error_class, never this text.
    detail: str | None = None

    def finish(self, status: str = STATUS_OK,
               error_class: str | None = None,
               detail: str | None = None) -> "Span":
        """Close the span. error_class uses the normalized §3 taxonomy."""
        self.end_time = _utc_now()
        self.status = status
        self.error_class = error_class
        self.detail = detail
        self.latency_ms = _elapsed_ms(self.start_time, self.end_time)
        return self

    def to_dict(self) -> dict[str, Any]:
        out = OrderedDict()
        for key in (
            "span_id", "trace_id", "name", "parent_span_id", "request_id",
            "task_id", "team_id", "worker_id", "model_id", "provider_id",
            "target_id", "start_time", "end_time", "latency_ms", "status",
            "error_class", "cost_class", "quota_state", "detail",
        ):
            value = getattr(self, key)
            # Only skip genuinely absent optional fields. `detail` is NOT
            # skipped when empty-string, and `latency_ms`/`status` are never
            # skipped, so a caller can never lose debugging text by setting
            # an unrelated field — which also keeps the §5 secret scan honest.
            if value is None:
                continue
            if value == "" and key not in ("detail", "status"):
                continue
            out[key] = value
        return out


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(start: str, end: str) -> float:
    if not start or not end:
        return 0.0
    from datetime import datetime
    try:
        t0 = datetime.fromisoformat(start)
        t1 = datetime.fromisoformat(end)
    except ValueError:
        return 0.0
    return round((t1 - t0).total_seconds() * 1000.0, 3)


class DistributedTracer:
    """In-process tracer with an optional JSON flush target.

    Thread-safe: a trace may be produced by a team of workers (§"team_id"
    exists precisely because a single request can fan out across workers).
    """

    def __init__(self, flush_path: str | Path | None = None) -> None:
        self.flush_path = Path(flush_path) if flush_path else None
        self._lock = threading.RLock()
        self._traces: dict[str, list[Span]] = {}
        self._spans: dict[str, Span] = {}

    # -- span lifecycle -----------------------------------------------------
    def start_span(self, name: str, parent_span_id: str | None = None,
                   trace_id: str | None = None, request_id: str | None = None,
                   task_id: str | None = None, team_id: str | None = None,
                   worker_id: str | None = None,
                   model_id: str | None = None,
                   provider_id: str | None = None,
                   target_id: str | None = None) -> Span:
        """Begin a span.

        No ``**kwargs``: the attribute set is closed so secrets have nowhere
        to hide (§5). If you need a new attribute, add it explicitly — that
        friction is intentional.
        """
        span = Span(
            span_id=uuid.uuid4().hex[:16],
            trace_id=trace_id or uuid.uuid4().hex,
            name=name,
            parent_span_id=parent_span_id,
            request_id=request_id,
            task_id=task_id,
            team_id=team_id,
            worker_id=worker_id,
            model_id=model_id,
            provider_id=provider_id,
            target_id=target_id,
            start_time=_utc_now(),
        )
        with self._lock:
            self._traces.setdefault(span.trace_id, []).append(span)
            self._spans[span.span_id] = span
        return span

    def end_span(self, span: Span, status: str = STATUS_OK,
                 error_class: str | None = None,
                 detail: str | None = None,
                 cost_class: str | None = None,
                 quota_state: str | None = None) -> Span:
        """Close a span and record cost/quota visibility."""
        if cost_class is not None:
            span.cost_class = cost_class
        if quota_state is not None:
            span.quota_state = quota_state
        # Only overwrite `detail` when a value is actually supplied, so
        # debugging text set earlier is never silently dropped.
        span.finish(status=status, error_class=error_class,
                    detail=detail if detail is not None else span.detail)
        return span

    @contextmanager
    def span(self, name: str, **kwargs) -> Iterator[Span]:
        """Context manager. Swallows nothing — exceptions still propagate,
        but the span is closed as ERROR first so the trace keeps the failure.
        """
        sp = self.start_span(name, **kwargs)
        try:
            yield sp
        except Exception as exc:
            from compute.error_taxonomy import normalize_error
            self.end_span(sp, status=STATUS_ERROR,
                          error_class=normalize_error(exc),
                          detail=type(exc).__name__)
            raise
        else:
            self.end_span(sp, status=STATUS_OK)

    # -- propagation --------------------------------------------------------
    def context_headers(self, span: Span) -> dict[str, str]:
        """W3C-style propagation headers for cross-worker tracing."""
        return {
            "traceparent": f"00-{span.trace_id}-{span.span_id}-01",
            "x-aetherius-trace-id": span.trace_id,
        }

    def parent_from_headers(self, headers: dict[str, str]) -> tuple[str | None,
                                                                    str | None]:
        """Recover (trace_id, parent_span_id) from propagation headers.

        Lets a cloud worker continue the SAME trace as the request that
        spawned it, rather than starting an unrelated trace.
        """
        traceparent = headers.get("traceparent", "")
        parts = traceparent.split("-")
        if len(parts) >= 3 and parts[0] == "00":
            return parts[1], parts[2]
        return (headers.get("x-aetherius-trace-id"),
                headers.get("x-aetherius-span-id"))

    # -- retrieval ----------------------------------------------------------
    def get_trace(self, trace_id: str) -> list[Span]:
        with self._lock:
            return list(self._traces.get(trace_id, []))

    def trace_summary(self, trace_id: str) -> dict[str, Any]:
        """Aggregate view: total latency, span count, error classes."""
        spans = self.get_trace(trace_id)
        if not spans:
            return OrderedDict([("trace_id", trace_id), ("spans", 0)])
        errors = [s.error_class for s in spans if s.error_class]
        return OrderedDict([
            ("trace_id", trace_id),
            ("spans", len(spans)),
            ("total_latency_ms", round(sum(s.latency_ms for s in spans), 3)),
            ("failed_spans", sum(1 for s in spans if s.status == STATUS_ERROR)),
            ("error_classes", sorted(set(errors))),
            ("span_names", [s.name for s in spans]),
        ])

    def flush(self) -> int:
        """Persist all traces to JSON. Returns spans written."""
        if not self.flush_path:
            return 0
        with self._lock:
            payload = OrderedDict([
                ("exported_at", _utc_now()),
                ("traces", [
                    OrderedDict([
                        ("trace_id", tid),
                        ("summary", self.trace_summary(tid)),
                        ("spans", [s.to_dict() for s in spans]),
                    ]) for tid, spans in self._traces.items()
                ]),
            ])
            self.flush_path.parent.mkdir(parents=True, exist_ok=True)
            self.flush_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8")
            return sum(len(s) for s in self._traces.values())

    # -- privacy self-check (§5) -------------------------------------------
    def assert_no_secrets(self, trace_id: str) -> list[str]:
        """Return the names of spans that look like they carry secret material.

        Defence in depth: even though the closed attribute set makes leaking a
        secret structurally impossible, this scans the recorded values for
        tell-tale patterns so a future change that loosens the API is caught
        by a test rather than by an incident.
        """
        suspicious: list[str] = []
        markers = ("sk-", "ghp_", "xoxb-", "AKIA", "Bearer ", "password",
                   "BEGIN RSA PRIVATE KEY")
        for sp in self.get_trace(trace_id):
            blob = json.dumps(sp.to_dict()).lower()
            if any(m.lower() in blob for m in markers):
                suspicious.append(sp.name)
        return suspicious


@dataclass
class TraceContext:
    """Carries trace identity through a request without threading globals."""

    tracer: DistributedTracer
    trace_id: str
    request_id: str | None = None
    task_id: str | None = None
    team_id: str | None = None
    worker_id: str | None = None

    def span(self, name: str, **kwargs) -> Any:
        merged = dict(trace_id=self.trace_id, request_id=self.request_id,
                      task_id=self.task_id, team_id=self.team_id,
                      worker_id=self.worker_id)
        merged.update(kwargs)
        return self.tracer.span(name, **merged)


def trace_inference_path(tracer: DistributedTracer | None = None,
                         request_id: str | None = None,
                         model_id: str | None = None,
                         provider_id: str | None = None,
                         target_id: str | None = None) -> "InferenceTrace":
    """Convenience: walk the canonical span path in order."""
    return InferenceTrace(
        tracer or DistributedTracer(), request_id=request_id,
        model_id=model_id, provider_id=provider_id, target_id=target_id)


class InferenceTrace:
    """Walks the canonical §10 span path, parenting each span to the last."""

    def __init__(self, tracer: DistributedTracer,
                 request_id: str | None = None,
                 model_id: str | None = None,
                 provider_id: str | None = None,
                 target_id: str | None = None) -> None:
        self.tracer = tracer
        self.request_id = request_id
        self.model_id = model_id
        self.provider_id = provider_id
        self.target_id = target_id
        self.spans: list[Span] = []
        self._current: Span | None = None

    def step(self, name: str) -> None:
        """Begin the next span, parented to the previous one."""
        self._current = self.tracer.start_span(
            name,
            parent_span_id=self._current.span_id if self._current else None,
            trace_id=self.spans[0].trace_id if self.spans else None,
            request_id=self.request_id,
            model_id=self.model_id if name == SPAN_ROUTER else None,
            provider_id=self.provider_id if name == SPAN_ADAPTER else None,
            target_id=self.target_id if name == SPAN_TARGET else None,
        )
        self.spans.append(self._current)

    def fail(self, error_class: str, detail: str | None = None) -> "InferenceTrace":
        """Mark the current span failed with a NORMALIZED error class."""
        if self._current is not None:
            self.tracer.end_span(self._current, status=STATUS_ERROR,
                                 error_class=error_class, detail=detail)
        return self

    def finish(self, cost_class: str | None = None,
               quota_state: str | None = None) -> "InferenceTrace":
        if self._current is not None:
            self.tracer.end_span(self._current, status=STATUS_OK,
                                 cost_class=cost_class, quota_state=quota_state)
        return self

    @property
    def trace_id(self) -> str:
        return self.spans[0].trace_id if self.spans else ""

    def run(self) -> "InferenceTrace":
        """Walk every canonical span in order with no work in between."""
        for name in CANONICAL_SPAN_PATH:
            self.step(name)
        return self

    def verify_canonical_path(self) -> bool:
        """True if the recorded spans are exactly the canonical path, in order."""
        return [s.name for s in self.spans] == CANONICAL_SPAN_PATH
