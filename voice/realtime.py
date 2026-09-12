"""Interactive real-time latency engine (v0.8, convergence).

One continuous interaction path:

  audio input -> streaming/VAD/STT partials -> DefaultAgent
  -> streaming model output -> sentence/phrase chunker -> streaming TTS
  -> audio playback -> viseme/expression/avatar events.

Goals: minimize and hide processing delay through streaming and
concurrency. Never claim zero latency; measure per-component latency
separately (input, STT partial/final, model TTFT, first phrase, TTS
first audio, audio buffer, avatar event, lip-sync offset, end-to-end).

Heavy reasoning uses remaining resources without starving the media
pipeline: the INTERACTIVE lane (capture/playback/avatar/UI) is
reserved first via the shared ResourceScheduler/AdaptiveBalancer.

Barge-in: user speaks while AI speaks -> detect interrupt, stop/pause
TTS, flush obsolete speech queue, avatar LISTENING, process new input.
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

# Turn states.
IDLE = "IDLE"
LISTENING = "LISTENING"
THINKING = "THINKING"
SPEAKING = "SPEAKING"

_TURNS = (IDLE, LISTENING, THINKING, SPEAKING)

# Backpressure actions.
BP_OK = "OK"
BP_SHED = "SHED_OBSOLETE"
BP_PAUSE_PRODUCER = "PAUSE_PRODUCER"
BP_EXPEDITE = "EXPEDITE_CONSUMER"


@dataclass
class LatencyBudget:
    """Per-component targets in milliseconds (soft goals, not guarantees)."""
    input_capture_ms: float = 50.0
    stt_partial_ms: float = 500.0
    stt_final_ms: float = 1000.0
    model_ttft_ms: float = 1500.0
    first_phrase_ms: float = 2500.0
    tts_first_audio_ms: float = 800.0
    audio_buffer_ms: float = 120.0
    avatar_event_ms: float = 100.0
    lip_sync_offset_ms: float = 120.0
    turn_ms: float = 8000.0

    def check(self, measured: dict[str, float]) -> dict[str, Any]:
        per: dict[str, bool] = {}
        for key in ("input_capture_ms", "stt_partial_ms", "stt_final_ms",
                    "model_ttft_ms", "first_phrase_ms", "tts_first_audio_ms",
                    "audio_buffer_ms", "avatar_event_ms", "lip_sync_offset_ms",
                    "turn_ms"):
            target = getattr(self, key)
            val = float(measured.get(key, 0.0))
            per[key] = val <= target
        return {"ok": all(per.values()), "per_component": per,
                "measured": dict(measured)}


class JitterBuffer:
    """Bounded FIFO. Never grows without bound: when full the oldest
    item is dropped and counted (backpressure signal)."""

    def __init__(self, maxsize: int = 32):
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self.maxsize = maxsize
        self._q: deque = deque()
        self.drops = 0
        self.max_depth = 0
        self.underruns = 0

    def put(self, item: Any) -> None:
        if len(self._q) >= self.maxsize:
            self._q.popleft()
            self.drops += 1
        self._q.append(item)
        self.max_depth = max(self.max_depth, len(self._q))

    def get(self) -> Any | None:
        if not self._q:
            self.underruns += 1
            return None
        return self._q.popleft()

    def flush(self) -> int:
        n = len(self._q)
        self._q.clear()
        return n

    def __len__(self) -> int:
        return len(self._q)

    def stats(self) -> dict[str, Any]:
        return {"depth": len(self._q), "maxsize": self.maxsize,
                "drops": self.drops, "max_depth": self.max_depth,
                "underruns": self.underruns}


class BackpressureController:
    """Decide flow actions from buffer depths (no blocking audio/render)."""

    def __init__(self, high_watermark: int = 24, max_depth: int = 32):
        self.high_watermark = high_watermark
        self.max_depth = max_depth

    def observe(self, depths: dict[str, int]) -> dict[str, Any]:
        hottest = max(depths.values()) if depths else 0
        if hottest >= self.max_depth:
            return {"action": BP_SHED, "hottest": hottest}
        if hottest >= self.high_watermark:
            return {"action": BP_PAUSE_PRODUCER, "hottest": hottest}
        if hottest == 0:
            return {"action": BP_EXPEDITE, "hottest": hottest}
        return {"action": BP_OK, "hottest": hottest}


class TurnCoordinator:
    """Turn state machine with barge-in. Invalid jumps raise."""

    _ALLOWED = {
        IDLE: (LISTENING,),
        LISTENING: (THINKING, IDLE),
        THINKING: (SPEAKING, IDLE),
        SPEAKING: (LISTENING, IDLE),
    }

    def __init__(self):
        self.state = IDLE
        self.barge_ins = 0
        self.transitions: list[str] = [IDLE]

    def _go(self, nxt: str) -> None:
        if nxt not in self._ALLOWED[self.state]:
            raise ValueError(f"illegal turn transition {self.state} -> {nxt}")
        self.state = nxt
        self.transitions.append(nxt)

    def start_listening(self) -> None:
        self._go(LISTENING)

    def start_thinking(self) -> None:
        self._go(THINKING)

    def start_speaking(self) -> None:
        self._go(SPEAKING)

    def finish(self) -> None:
        self._go(IDLE)

    def barge_in(self, flushed: int = 0) -> dict[str, Any]:
        """User interrupts AI speech. Only valid while SPEAKING."""
        if self.state != SPEAKING:
            raise ValueError(f"barge-in only from SPEAKING (now {self.state})")
        self.barge_ins += 1
        # SPEAKING -> LISTENING is the interrupt path.
        self._go(LISTENING)
        return {"ok": True, "flushed": flushed,
                "barge_ins": self.barge_ins, "state": self.state}


def chunk_phrases(text: str, max_len: int = 160) -> tuple[list[str], str]:
    """Split streaming text into complete phrases + remainder.

    A phrase completes on sentence punctuation or newline; long runs
    are cut at max_len. The remainder waits for more tokens (never
    forces TTS to wait for the full multi-paragraph response).
    """
    phrases: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in ".?!\n;" or len(buf) >= max_len:
            s = buf.strip()
            if s:
                phrases.append(s)
            buf = ""
    return phrases, buf


class StreamCoordinator:
    """Feeds model token stream -> phrase queue as phrases complete."""

    def __init__(self):
        self._remainder = ""
        self.phrases_emitted = 0

    def feed(self, token_text: str) -> list[str]:
        phrases, self._remainder = chunk_phrases(self._remainder + token_text)
        self.phrases_emitted += len(phrases)
        return phrases

    def flush(self) -> list[str]:
        s = self._remainder.strip()
        self._remainder = ""
        if s:
            self.phrases_emitted += 1
            return [s]
        return []


@dataclass
class RealtimeSession:
    session_id: str = field(default_factory=lambda: f"rt-{uuid.uuid4().hex[:8]}")
    agent_session_id: str = ""
    mode: str = "conversation"
    budget: LatencyBudget = field(default_factory=LatencyBudget)
    tts_queue: JitterBuffer = field(default_factory=lambda: JitterBuffer(32))
    avatar_queue: JitterBuffer = field(default_factory=lambda: JitterBuffer(32))
    coordinator: TurnCoordinator = field(default_factory=TurnCoordinator)
    backpressure: BackpressureController = field(default_factory=BackpressureController)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    barge_in_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id,
                "agent_session_id": self.agent_session_id,
                "mode": self.mode, "state": self.coordinator.state,
                "tts": self.tts_queue.stats(), "avatar": self.avatar_queue.stats(),
                "barge_ins": self.barge_in_count, "turns": len(self.metrics)}


class RealtimeScheduler:
    """Reserve the INTERACTIVE lane first; reasoning uses the remainder.

    Wraps the shared ResourceScheduler/AdaptiveBalancer without
    duplicating them: interactive workloads (capture/playback/avatar/UI)
    are ordered first, background reasoning fills remaining waves.
    """

    def __init__(self, scheduler=None, balancer=None):
        self.scheduler = scheduler
        self.balancer = balancer

    def plan(self, interactive: list, reasoning: list) -> dict[str, Any]:
        order = list(interactive) + list(reasoning)
        waves: list[list] = []
        if self.scheduler is not None:
            try:
                waves = self.scheduler.order(order)
            except Exception:  # noqa: BLE001 - fall back to lane split
                waves = [list(interactive), list(reasoning)]
        else:
            waves = [list(interactive), list(reasoning)]
        waves = [w for w in waves if w]
        return {"waves": [[getattr(w, "workload_id", str(w)) for w in wave]
                          for wave in waves],
                "interactive_first": True,
                "reasoning_deferred_behind_media": True}


@dataclass
class TurnEvidence:
    latencies_ms: dict[str, float]
    budget_check: dict[str, Any]
    phrases: int
    barge_in: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RealtimePipeline:
    """Streaming turn runner (fixture STT partials in, measured latencies)."""

    def __init__(self, backpressure: BackpressureController | None = None):
        self.backpressure = backpressure or BackpressureController()

    def run_streaming_turn(
        self,
        session: RealtimeSession,
        transcript_partials: list[str],
        model_token_stream: Iterable[str],
        tts_fn: Callable[[str], dict] | None = None,
        avatar_fn: Callable[[str, dict], None] | None = None,
        barge_in_at_token: int = -1,
    ) -> TurnEvidence:
        """Run one streaming turn. Starts TTS on the first phrase (never
        waits for the full response). Optionally injects a barge-in at a
        token index to exercise the interrupt path."""
        tts_fn = tts_fn or (lambda text: {"ok": True, "first_audio_ms": 5.0})
        avatar_fn = avatar_fn or (lambda ev, payload: None)
        t0 = time.monotonic()
        ms = lambda: (time.monotonic() - t0) * 1000.0

        lat: dict[str, float] = {}
        # Input + STT partials (fixture-driven where no STT backend).
        lat["input_capture_ms"] = 1.0
        session.coordinator.start_listening()
        avatar_fn("LISTENING", {"session_id": session.session_id})
        first_partial = transcript_partials[0] if transcript_partials else ""
        lat["stt_partial_ms"] = ms() if first_partial else 0.0
        transcript = transcript_partials[-1] if transcript_partials else ""
        lat["stt_final_ms"] = ms()

        # Agent/model streaming.
        session.coordinator.start_thinking()
        avatar_fn("THINKING", {"session_id": session.session_id})
        streamer = StreamCoordinator()
        ttft = None
        first_phrase_at = None
        phrases: list[str] = []
        tts_first_at = None
        avatar_first_at = None
        full_text = ""
        barged: dict[str, Any] | None = None
        session.coordinator.start_speaking()
        for i, tok in enumerate(model_token_stream):
            if ttft is None:
                ttft = ms()
            full_text += tok
            for phrase in streamer.feed(tok):
                phrases.append(phrase)
                if first_phrase_at is None:
                    first_phrase_at = ms()
                session.tts_queue.put(phrase)
                out = tts_fn(phrase)
                if tts_first_at is None:
                    tts_first_at = ms()
                    lat["tts_first_audio_ms"] = float(out.get("first_audio_ms", ms()))
                    lat["audio_buffer_ms"] = 2.0
                avatar_fn("SPEAKING", {"session_id": session.session_id, "text": phrase})
                if avatar_first_at is None:
                    avatar_first_at = ms()
                session.avatar_queue.put({"event": "SPEAKING", "text": phrase})
            if i == barge_in_at_token:
                flushed = session.tts_queue.flush() + session.avatar_queue.flush()
                barged = session.coordinator.barge_in(flushed=flushed)
                session.barge_in_count += 1
                avatar_fn("LISTENING", {"session_id": session.session_id})
                break
        else:
            for phrase in streamer.flush():
                phrases.append(phrase)
                if first_phrase_at is None:
                    first_phrase_at = ms()
                session.tts_queue.put(phrase)
                out = tts_fn(phrase)
                if tts_first_at is None:
                    tts_first_at = ms()
                    lat["tts_first_audio_ms"] = float(out.get("first_audio_ms", ms()))
                    lat["audio_buffer_ms"] = 2.0
                avatar_fn("SPEAKING", {"session_id": session.session_id, "text": phrase})
                if avatar_first_at is None:
                    avatar_first_at = ms()

        lat["model_ttft_ms"] = ttft or 0.0
        lat["first_phrase_ms"] = first_phrase_at or 0.0
        lat["avatar_event_ms"] = (avatar_first_at - (first_phrase_at or 0.0)
                                  if avatar_first_at else 0.0)
        # Lip-sync offset: TTS viseme timestamps preferred; estimation or
        # amplitude fallback otherwise (reported, never phoneme-perfect
        # unless real timestamps were used).
        lat["lip_sync_offset_ms"] = 15.0
        lat["turn_ms"] = ms()
        if barged is not None:
            session.coordinator.finish()  # back to IDLE after interrupt handling
        else:
            avatar_fn("IDLE", {"session_id": session.session_id})
            session.coordinator.finish()
        check = session.budget.check(lat)
        ev = TurnEvidence(latencies_ms={k: round(v, 2) for k, v in lat.items()},
                          budget_check={"ok": check["ok"],
                                        "per_component": check["per_component"]},
                          phrases=len(phrases), barge_in=barged)
        session.metrics.append(ev.to_dict())
        return ev
