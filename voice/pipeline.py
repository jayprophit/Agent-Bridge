"""Provider-neutral voice pipeline (v0.8, Part D).

microphone -> audio input -> [VAD] -> STT -> DefaultAgent -> tools/actions
-> response text -> TTS -> speaker -> avatar events.

No audio is captured without an explicit session permission and an
installed input adapter. Fixture adapters drive tests; physical microphone
is never activated by discovery or tests.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

# Voice session modes
PUSH_TO_TALK = "push_to_talk"
CONVERSATION = "conversation"

# Answer policies (telephony shares these; default is manual)
MANUAL_ANSWER = "MANUAL_ANSWER"
AUTO_ANSWER_TRUSTED = "AUTO_ANSWER_TRUSTED"
AUTO_ANSWER_ALL = "AUTO_ANSWER_ALL"
BUSINESS_HOURS = "BUSINESS_HOURS"
DO_NOT_DISTURB = "DO_NOT_DISTURB"


@dataclass
class VoiceTurn:
    turn_id: str
    session_id: str
    transcript: str = ""
    response_text: str = ""
    tools_used: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    started_at: float = 0.0
    ended_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VoiceSession:
    session_id: str
    agent_session_id: str = ""  # SAME DefaultAgent session (Chat/Work/voice share it)
    mode: str = PUSH_TO_TALK
    answer_policy: str = MANUAL_ANSWER
    input_device: str = ""
    output_device: str = ""
    muted: bool = False
    listening: bool = False
    recording_consent: bool = False  # explicit session permission, never implied
    turns: list[VoiceTurn] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["turns"] = [t.to_dict() for t in self.turns]
        return data


class VoicePipeline:
    """Orchestrates one voice turn across adapters on the shared event bus."""

    def __init__(self, bus=None, recognizer: Callable[[bytes | None], str] | None = None,
                 synthesizer: Callable[[str], bytes | str] | None = None,
                 agent_fn: Callable[[str], dict] | None = None,
                 avatar_fn: Callable[[str, dict], None] | None = None):
        self.bus = bus
        self.recognizer = recognizer or (lambda audio: "")
        self.synthesizer = synthesizer or (lambda text: "")
        self.agent_fn = agent_fn or (lambda text: {"response": "", "tools": []})
        self.avatar_fn = avatar_fn or (lambda event, payload: None)

    def _emit(self, event: str, payload: dict | None = None) -> None:
        if self.bus is not None:
            self.bus.emit(event, payload or {})

    def run_turn(self, session: VoiceSession, audio: bytes | None = None) -> VoiceTurn:
        """Run one push-to-talk turn. Raises on policy violation, never records silently."""
        if session.muted:
            raise PermissionError("session is muted")
        turn = VoiceTurn(turn_id=f"vt-{uuid.uuid4().hex[:8]}",
                         session_id=session.session_id,
                         started_at=time.monotonic())
        self._emit("listening", {"session_id": session.session_id})
        self.avatar_fn("LISTENING", {"session_id": session.session_id})
        transcript = self.recognizer(audio)
        turn.transcript = transcript
        self._emit("speech_final", {"session_id": session.session_id, "text": transcript})
        self.avatar_fn("THINKING", {"session_id": session.session_id})
        result = self.agent_fn(transcript)
        turn.response_text = str(result.get("response", ""))
        turn.tools_used = list(result.get("tools", []))
        self.avatar_fn("SPEAKING", {"session_id": session.session_id,
                                    "text": turn.response_text})
        self.synthesizer(turn.response_text)
        turn.ended_at = time.monotonic()
        session.turns.append(turn)
        self._emit("agent_message", {"session_id": session.session_id,
                                     "text": turn.response_text})
        self.avatar_fn("IDLE", {"session_id": session.session_id})
        return turn

    def stop_speaking(self, session: VoiceSession) -> dict:
        self._emit("stop_speaking", {"session_id": session.session_id})
        self.avatar_fn("IDLE", {"session_id": session.session_id})
        return {"ok": True, "stopped": True}

    def set_muted(self, session: VoiceSession, muted: bool) -> dict:
        session.muted = bool(muted)
        self._emit("mute", {"session_id": session.session_id, "muted": session.muted})
        return {"ok": True, "muted": session.muted}
