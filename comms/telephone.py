"""Provider-neutral telephony architecture (v0.8, Part F).

The same DefaultAgent drives telephone calls through adapters. Real PSTN
access stays PROVIDER_REQUIRED until a provider/account/number is
configured. Calls are never auto-answered by default; recording and
transcription are policy-controlled, never silent.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

# Call states
RINGING = "ringing"
ANSWERED = "answered"
REJECTED = "rejected"
ACTIVE = "active"
HANGUP = "hangup"
ESCALATED = "escalated"

# Answer policies (default: manual)
MANUAL_ANSWER = "MANUAL_ANSWER"
AUTO_ANSWER_TRUSTED = "AUTO_ANSWER_TRUSTED"
AUTO_ANSWER_ALL = "AUTO_ANSWER_ALL"
BUSINESS_HOURS = "BUSINESS_HOURS"
DO_NOT_DISTURB = "DO_NOT_DISTURB"


@dataclass
class CallSession:
    call_id: str
    agent_session_id: str = ""  # SAME DefaultAgent session (chat/voice/call share it)
    direction: str = "inbound"  # inbound | outbound
    state: str = RINGING
    caller: str = ""
    answer_policy: str = MANUAL_ANSWER
    recording_consent: bool = False
    transcript: list[dict[str, str]] = field(default_factory=list)
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def duration_s(self) -> float:
        if self.started_at and self.ended_at:
            return round(self.ended_at - self.started_at, 2)
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["duration_s"] = self.duration_s
        return data


class CallProvider:
    """Provider interface: SIP/WebRTC/Twilio-style/PSTN adapters implement this."""

    provider_id: str = "base"

    def place_call(self, to: str, **kwargs) -> dict:
        raise NotImplementedError("outbound calls need a configured provider")

    def answer(self, call_id: str) -> dict:
        raise NotImplementedError

    def hangup(self, call_id: str) -> dict:
        raise NotImplementedError

    def send_audio(self, call_id: str, audio: bytes) -> dict:
        raise NotImplementedError

    def dtmf(self, call_id: str, digits: str) -> dict:
        raise NotImplementedError


class LoopbackCallProvider(CallProvider):
    """Mock/loopback provider for tests. Never touches PSTN."""

    provider_id = "loopback-mock"

    def __init__(self):
        self.calls: dict[str, dict] = {}
        self.sent_audio: list[tuple[str, bytes]] = []

    def incoming(self, caller: str = "mock-caller") -> str:
        call_id = f"call-{uuid.uuid4().hex[:8]}"
        self.calls[call_id] = {"state": RINGING, "caller": caller}
        return call_id

    def place_call(self, to: str, **kwargs) -> dict:
        call_id = f"call-{uuid.uuid4().hex[:8]}"
        self.calls[call_id] = {"state": ACTIVE, "caller": to}
        return {"ok": True, "call_id": call_id, "mock": True}

    def answer(self, call_id: str) -> dict:
        self.calls[call_id]["state"] = ANSWERED
        return {"ok": True, "call_id": call_id, "mock": True}

    def hangup(self, call_id: str) -> dict:
        self.calls[call_id]["state"] = HANGUP
        return {"ok": True, "call_id": call_id, "mock": True}

    def send_audio(self, call_id: str, audio: bytes) -> dict:
        self.sent_audio.append((call_id, audio))
        return {"ok": True, "bytes": len(audio), "mock": True}

    def dtmf(self, call_id: str, digits: str) -> dict:
        return {"ok": True, "digits": digits, "mock": True}


class TelephoneAgent:
    """Call lifecycle driven by policy + DefaultAgent callback."""

    def __init__(self, provider: CallProvider | None = None,
                 bus=None,
                 agent_fn: Callable[[str], dict] | None = None,
                 tts_fn: Callable[[str], bytes | str] | None = None,
                 stt_fn: Callable[[bytes | None], str] | None = None):
        self.provider = provider or LoopbackCallProvider()
        self.bus = bus
        self.agent_fn = agent_fn or (lambda text: {"response": "", "tools": []})
        self.tts_fn = tts_fn or (lambda text: "")
        self.stt_fn = stt_fn or (lambda audio: "")
        self.sessions: dict[str, CallSession] = {}

    def _emit(self, event: str, payload: dict | None = None) -> None:
        if self.bus is not None:
            self.bus.emit(event, payload or {})

    def on_incoming(self, call_id: str, caller: str,
                    policy: str = MANUAL_ANSWER) -> CallSession:
        """Apply the answer policy. Default never auto-answers."""
        session = CallSession(call_id=call_id, caller=caller,
                              answer_policy=policy, started_at=time.monotonic())
        if policy == DO_NOT_DISTURB:
            session.state = REJECTED
        elif policy == AUTO_ANSWER_ALL:
            session.state = ANSWERED
        elif policy == MANUAL_ANSWER:
            session.state = RINGING  # waits for explicit answer
        else:
            session.state = RINGING
        self.sessions[call_id] = session
        self._emit("call_event", {"call_id": call_id, "state": session.state})
        return session

    def answer(self, session: CallSession) -> dict:
        res = self.provider.answer(session.call_id)
        if res.get("ok"):
            session.state = ANSWERED
            self._emit("call_event", {"call_id": session.call_id, "state": ANSWERED})
        return res

    def run_exchange(self, session: CallSession, caller_audio: bytes | None = None,
                     record: bool = False) -> dict:
        """One STT -> agent -> TTS exchange. Recording needs consent."""
        if record and not session.recording_consent:
            raise PermissionError("call recording requires explicit consent")
        transcript = self.stt_fn(caller_audio)
        if record:
            session.transcript.append({"from": "caller", "text": transcript})
        result = self.agent_fn(transcript)
        reply = str(result.get("response", ""))
        self.tts_fn(reply)
        if isinstance(self.provider, LoopbackCallProvider):
            self.provider.send_audio(session.call_id, reply.encode()[:64])
        if record:
            session.transcript.append({"from": "agent", "text": reply})
        session.state = ACTIVE
        self._emit("call_event", {"call_id": session.call_id, "state": ACTIVE})
        return {"ok": True, "transcript": transcript, "reply": reply,
                "tools": list(result.get("tools", []))}

    def hangup(self, session: CallSession, summary: str = "") -> dict:
        res = self.provider.hangup(session.call_id)
        session.state = HANGUP
        session.ended_at = time.monotonic()
        self._emit("call_event", {"call_id": session.call_id, "state": HANGUP,
                                  "duration_s": session.duration_s})
        return {"ok": res.get("ok", False), "summary": summary,
                "duration_s": session.duration_s,
                "transcript": list(session.transcript)}

    def escalate(self, session: CallSession, reason: str = "") -> dict:
        session.state = ESCALATED
        self._emit("call_event", {"call_id": session.call_id, "state": ESCALATED,
                                  "reason": reason})
        return {"ok": True, "escalated": True, "reason": reason}
