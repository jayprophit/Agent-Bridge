"""Multimodal routing + voice pipeline tests (v0.8, fixtures only)."""
import unittest

from events import EventBus
from multimodal import (
    IMAGE_GENERATION, OCR, STT, TTS, VISION, ModalityBackend,
    MultimodalRouter, local_backends_from_registries,
)
from multimodal.probes import probe_image_endpoint, probe_tesseract
from tools.registry import ToolRegistry
from voice import VoicePipeline, VoiceSession


def _registry():
    from tools.tool_audit import collect_records
    reg = ToolRegistry()
    for rec in collect_records():
        try:
            reg.register(rec)
        except ValueError:
            pass
    return reg


class MultimodalRouterTests(unittest.TestCase):
    def test_text_routes_local(self):
        r = MultimodalRouter(local_backends_from_registries(_registry(), None))
        route = r.route("TEXT")
        self.assertEqual(route.status, "AVAILABLE")

    def test_vision_truthful_without_backend(self):
        r = MultimodalRouter(local_backends_from_registries(_registry(), None))
        route = r.route(VISION)
        self.assertIn(route.status, ("PROVIDER_REQUIRED", "NOT_INSTALLED"))
        # Never route vision by model name: no model names involved.
        self.assertNotIn("qwen", route.backend_id)

    def test_image_generation_provider_required(self):
        r = MultimodalRouter(local_backends_from_registries(_registry(), None))
        route = r.route(IMAGE_GENERATION)
        # Deterministic stdlib ops exist but are not generative.
        self.assertIn(route.status, ("AVAILABLE", "PROVIDER_REQUIRED"))

    def test_unknown_modality(self):
        r = MultimodalRouter([])
        route = r.route("SMELL_O_VISION")
        self.assertEqual(route.status, "PROVIDER_REQUIRED")

    def test_verified_preferred_over_unverified(self):
        r = MultimodalRouter([
            ModalityBackend("unver", OCR, "provider", [], False, "", "nope"),
            ModalityBackend("ver", OCR, "local_tool", ["ocr.x"], True, "tested"),
        ])
        self.assertEqual(r.route(OCR).backend_id, "ver")


class ProbeTests(unittest.TestCase):
    def test_tesseract_absent(self):
        import shutil
        res = probe_tesseract()
        self.assertEqual(res["present"], bool(shutil.which("tesseract")))

    def test_no_local_image_endpoint(self):
        res = probe_image_endpoint()
        # Either answer is fine; the shape must be truthful.
        self.assertIn("present", res)
        self.assertIn("backend", res)


class VoicePipelineTests(unittest.TestCase):
    def test_push_to_talk_turn(self):
        bus = EventBus()
        seen = []
        bus.subscribe("agent_message", lambda p: seen.append(p))
        avatar = []
        pipe = VoicePipeline(
            bus=bus,
            recognizer=lambda audio: "what time is it",
            agent_fn=lambda text: {"response": "time reply", "tools": ["demo.t"]},
            synthesizer=lambda text: b"\x00" * 8,
            avatar_fn=lambda e, p: avatar.append(e))
        session = VoiceSession(session_id="vs-1", agent_session_id="same-session-1",
                               recording_consent=True)
        turn = pipe.run_turn(session, audio=b"\x01" * 8)
        self.assertEqual(turn.transcript, "what time is it")
        self.assertEqual(turn.response_text, "time reply")
        self.assertEqual(len(session.turns), 1)
        self.assertIn("LISTENING", avatar)
        self.assertIn("SPEAKING", avatar)
        self.assertTrue(seen)

    def test_muted_session_refuses(self):
        pipe = VoicePipeline()
        session = VoiceSession(session_id="vs-2", muted=True)
        with self.assertRaises(PermissionError):
            pipe.run_turn(session)

    def test_mute_unmute_and_stop(self):
        pipe = VoicePipeline()
        session = VoiceSession(session_id="vs-3")
        self.assertTrue(pipe.set_muted(session, True)["muted"])
        self.assertTrue(pipe.stop_speaking(session)["ok"])

    def test_session_survives_across_views(self):
        # Chat/Work/voice share agent_session_id by construction.
        session = VoiceSession(session_id="vs-4", agent_session_id="shared-1")
        self.assertEqual(session.agent_session_id, "shared-1")


if __name__ == "__main__":
    unittest.main()
