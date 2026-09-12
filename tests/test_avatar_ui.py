"""Avatar protocol + reference UI + IDE embedding + event unity tests (v0.8)."""
import json
import os
import struct
import unittest

from avatar import (
    AVATAR_EVENTS, CUSTOM, FEMALE, MALE, NEUTRAL, VISEME_JAW,
    AvatarEvent, AvatarProfile, amplitude_to_jaw,
)
from events import EventBus
from ides.embedding import (
    EMBEDDED_IDE_LEFT, HEADLESS, DiffApproval, HostContext,
    ReferenceIDEAdapter,
)

UI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "ui")


class AvatarProtocolTests(unittest.TestCase):
    def test_all_events_validate(self):
        for event in AVATAR_EVENTS:
            ev = AvatarEvent(event=event, session_id="s1")
            if event == "EMOTION":
                ev.emotion = "happy"
            if event == "VISEME":
                ev.viseme = "aa"
            self.assertTrue(ev.validate()[0], event)

    def test_unknown_event_rejected(self):
        self.assertFalse(AvatarEvent(event="DANCE_PARTY").validate()[0])

    def test_bad_expression_rejected(self):
        self.assertFalse(AvatarEvent(event="EMOTION", emotion="theatrical").validate()[0])

    def test_bad_viseme_rejected(self):
        self.assertFalse(AvatarEvent(event="VISEME", viseme="XX").validate()[0])

    def test_viseme_jaw_map_covers_all(self):
        from avatar import VISEMES
        for v in VISEMES:
            self.assertIn(v, VISEME_JAW)
            self.assertGreaterEqual(VISEME_JAW[v], 0.0)
            self.assertLessEqual(VISEME_JAW[v], 1.0)

    def test_amplitude_fallback_clamped(self):
        self.assertEqual(amplitude_to_jaw(2.0), 1.0)
        self.assertEqual(amplitude_to_jaw(-1.0), 0.0)

    def test_presentation_explicit_not_pitch(self):
        for profile in (MALE, FEMALE, NEUTRAL, CUSTOM):
            self.assertTrue(AvatarProfile(presentation=profile).validate()[0])
        self.assertFalse(AvatarProfile(presentation="FROM_VOICE").validate()[0])
        import dataclasses
        # No pitch-derived field may exist on the profile: presentation is
        # explicit configuration only.
        self.assertNotIn("pitch", {f.name for f in dataclasses.fields(AvatarProfile)})

    def test_reference_glb_valid(self):
        path = os.path.join(UI, "assets", "reference-avatar.glb")
        self.assertTrue(os.path.exists(path))
        with open(path, "rb") as f:
            data = f.read()
        magic, ver, total = struct.unpack("<III", data[:12])
        self.assertEqual((hex(magic), ver, total), ("0x46546c67", 2, len(data)))
        ln, _ = struct.unpack("<II", data[12:20])
        gltf = json.loads(data[20:20 + ln])
        names = [n["name"] for n in gltf["nodes"]]
        for required in ("Head", "Jaw", "EyeL", "EyeR"):
            self.assertIn(required, names)


class ReferenceUITests(unittest.TestCase):
    def test_ui_files_present(self):
        for fn in ("index.html", "app.js", "avatar.js",
                   os.path.join("assets", "reference-avatar.glb")):
            self.assertTrue(os.path.exists(os.path.join(UI, fn)), fn)

    def _read(self, fn):
        with open(os.path.join(UI, fn), encoding="utf-8") as f:
            return f.read()

    def test_no_external_model_assets(self):
        for fn in ("index.html", "app.js", "avatar.js"):
            text = self._read(fn)
            self.assertNotIn(".glb", text.replace("reference-avatar.glb", ""))
            for ext in (".vrm", ".fbx", ".obj"):
                self.assertNotIn(ext, text.lower())

    def test_three_isolated_with_offline_fallback(self):
        app = self._read("avatar.js")
        self.assertIn("Renderer2D", app)
        self.assertIn("useThreeRenderer", app)
        self.assertIn("window.THREE", app)

    def test_chat_work_share_session(self):
        app = self._read("app.js")
        # View switch must not mint a new session id.
        self.assertNotIn("Math.random", app.split("setView")[1].split("function")[0])


class IDEEmbeddingTests(unittest.TestCase):
    def test_host_context_validates(self):
        ctx = HostContext(ide_id="vscode", workspace_root="C:\\proj",
                          host_mode=EMBEDDED_IDE_LEFT, session_id="shared-1")
        self.assertTrue(ctx.validate()[0])
        ctx.host_mode = "NOPE"
        self.assertFalse(ctx.validate()[0])

    def test_reference_adapter_is_interface_only(self):
        adapter = ReferenceIDEAdapter()
        with self.assertRaises(NotImplementedError):
            adapter.host_context()

    def test_diff_approval_shape(self):
        d = DiffApproval(diff_id="d1", session_id="shared-1", files=["a.py"])
        self.assertEqual(d.to_dict()["session_id"], "shared-1")


class EventUnityTests(unittest.TestCase):
    def test_one_session_across_surfaces(self):
        # Chat, voice, call and IDE panels share agent_session_id over one bus.
        from voice import VoiceSession
        from comms import CallSession
        from ides.embedding import HostContext
        bus = EventBus()
        seen = []
        for evt in ("agent_message", "call_event"):
            bus.subscribe(evt, lambda p, e=evt: seen.append((e, p)))
        voice_session = VoiceSession(session_id="vs-1", agent_session_id="shared-1")
        call = CallSession(call_id="c-1", agent_session_id="shared-1")
        host = HostContext(ide_id="vscode", session_id="shared-1")
        bus.emit("agent_message", {"session_id": "shared-1"})
        bus.emit("call_event", {"session_id": "shared-1"})
        self.assertEqual(voice_session.agent_session_id, call.agent_session_id)
        self.assertEqual(call.agent_session_id, host.session_id)
        self.assertEqual(len(seen), 2)


if __name__ == "__main__":
    unittest.main()
