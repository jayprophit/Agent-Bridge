"""Distributed tracing for the Aetherius AI Gateway (§114).

OpenTelemetry-compatible conventions, local-first. Tracks the full inference
pipeline: request → authorization → privacy → cost → ModelRouter →
execution target → provider adapter → response → evidence.

No paid service required. Spans are collected in-memory and can be
serialized to JSON for evidence retention.
"""
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Span:
    """A single tracing span (§114)."""
    trace_id: str
    span_id: str
    parent_span_id: str
    operation: str
    start: float
    end: float = 0.0
    duration_ms: int = 0
    status: str = "OK"  # OK, ERROR, TIMEOUT, CANCELLED
    model_id: Optional[str] = None
    provider_id: Optional[str] = None
    target_id: Optional[str] = None
    worker_id: Optional[str] = None
    team_id: Optional[str] = None
    request_id: Optional[str] = None
    task_id: Optional[str] = None
    cost_class: Optional[str] = None
    quota_state: Optional[str] = None
    normalized_error: Optional[str] = None
    attributes: dict = field(default_factory=dict)

    def end(self, status: str = "OK", error: str | None = None) -> None:
        self.end = time.time()
        self.duration_ms = int((self.end - self.start) * 1000)
        self.status = status
        if error:
            self.normalized_error = error


@dataclass
class Trace:
    """A complete trace containing all spans for one request."""
    trace_id: str
    root_span_id: str
    request_id: Optional[str] = None
    task_id: Optional[str] = None
    team_id: Optional[str] = None
    spans: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class TraceCollector:
    """In-memory span collector with JSON export for evidence retention.

    Local-first: no external service required. Can be extended later
    to export to an actual OTLP collector if the owner authorises one.
    """

    def __init__(self) -> None:
        self._traces: dict[str, Trace] = {}
        self._spans: dict[str, Span] = {}  # span_id -> Span

    def start_span(self, operation: str, parent_span_id: str = "",
                   trace_id: str = "", **attrs) -> Span:
        span_id = uuid.uuid4().hex[:12]
        if not trace_id:
            trace_id = uuid.uuid4().hex[:16]
        # Resolve parent_span_id if it's a Span object
        if hasattr(parent_span_id, "span_id"):
            parent_span_id = parent_span_id.span_id
        if not parent_span_id:
            # This is a root span
            if trace_id not in self._traces:
                self._traces[trace_id] = Trace(trace_id=trace_id, root_span_id=span_id)
            else:
                if not self._traces[trace_id].root_span_id:
                    self._traces[trace_id].root_span_id = span_id

        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id or self._traces.get(trace_id, Trace(trace_id, span_id)).root_span_id,
            operation=operation,
            start=time.time(),
            end=0.0,
            duration_ms=0,
            status="OK",
            attributes=attrs,
        )
        self._spans[span_id] = span
        if trace_id in self._traces:
            self._traces[trace_id].spans.append(span)
            # Propagate request_id/task_id/team_id from attrs to the Trace
            for k in ("request_id", "task_id", "team_id"):
                if k in attrs and not getattr(self._traces[trace_id], k):
                    setattr(self._traces[trace_id], k, attrs[k])
        return span

    def end_span(self, span: Span, status: str = "OK", error: str | None = None) -> None:
        span.end = time.time()
        span.duration_ms = int((span.end - span.start) * 1000)
        span.status = status
        if error:
            span.normalized_error = error

    def complete_span(self, operation: str, **attrs) -> Span:
        """Create and immediately complete a span for a quick operation."""
        span = self.start_span(operation, **attrs)
        self.end_span(span)
        return span

    def export_trace(self, trace_id: str) -> dict:
        """Export a trace to a serializable dict for evidence retention."""
        tr = self._traces.get(trace_id)
        if not tr:
            return {}
        return {
            "trace_id": tr.trace_id,
            "root_span_id": tr.root_span_id,
            "request_id": tr.request_id,
            "task_id": tr.task_id,
            "team_id": tr.team_id,
            "created_at": tr.created_at,
            "spans": [asdict(s) for s in tr.spans if s.trace_id == trace_id],
        }

    def all_traces(self) -> list[dict]:
        return [self.export_trace(tid) for tid in self._traces]


def create_trace(tracer: TraceCollector, operation: str, **attrs) -> Span:
    """Convenience: start a root span."""
    return tracer.start_span(operation, **attrs)
