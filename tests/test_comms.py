"""Email + telephony tests (v0.8). No real sends, no real calls."""
import unittest

from comms import (
    DO_NOT_DISTURB, MANUAL_ANSWER, LoopbackCallProvider, TelephoneAgent,
)
from comms.telephone import ANSWERED, HANGUP, REJECTED, RINGING
from tools.registry import ToolRegistry
from tools.router import ToolRouter


def _email_registry():
    from tools.cat_comms import email_records, telephone_records
    reg = ToolRegistry()
    for rec in list(email_records()) + list(telephone_records()):
        try:
            reg.register(rec)
        except ValueError:
            pass
    return reg


class EmailToolTests(unittest.TestCase):
    def test_draft_tools_exist_and_send_is_gated(self):
        reg = _email_registry()
        for tid in ("email.compose", "email.draft", "email.send",
                    "email.read", "email.reply"):
            self.assertIn(tid, reg.ids())
        send = reg.get("email.send")
        self.assertEqual(send.status, "PROVIDER_REQUIRED")
        self.assertFalse(send.available)
        self.assertIn("OWNER_FULL_ACCESS", send.supported_profiles)

    def test_no_duplicate_email_send(self):
        reg = _email_registry()
        sends = [t for t in reg.ids() if "send" in t and t.startswith("email")]
        self.assertEqual(sends, ["email.send"])

    def test_no_credentials_in_tree(self):
        import os
        hits = []
        for dirpath, _, filenames in os.walk("tools"):
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                    text = f.read().lower()
                for needle in ("smtp_password", "api_key=", "client_secret"):
                    if needle in text:
                        hits.append(os.path.join(dirpath, fn) + ":" + needle)
        self.assertEqual(hits, [])


class TelephoneLifecycleTests(unittest.TestCase):
    def test_full_mock_call_lifecycle(self):
        from events import EventBus
        bus = EventBus()
        events = []
        bus.subscribe("call_event", lambda p: events.append(p))
        provider = LoopbackCallProvider()
        agent = TelephoneAgent(
            provider=provider, bus=bus,
            agent_fn=lambda text: {"response": "mock reply", "tools": []},
            tts_fn=lambda text: b"\x00" * 4,
            stt_fn=lambda audio: "mock caller speech")
        call_id = provider.incoming("mock-caller")
        session = agent.on_incoming(call_id, "mock-caller", MANUAL_ANSWER)
        self.assertEqual(session.state, RINGING)  # never auto-answered
        agent.answer(session)
        self.assertEqual(session.state, ANSWERED)
        session.recording_consent = True
        out = agent.run_exchange(session, caller_audio=b"\x01" * 4, record=True)
        self.assertTrue(out["ok"])
        self.assertEqual(out["transcript"], "mock caller speech")
        done = agent.hangup(session, summary="mock summary")
        self.assertEqual(session.state, HANGUP)
        self.assertGreaterEqual(done["duration_s"], 0)
        self.assertTrue(any(e["state"] == HANGUP for e in events))
        # No PSTN involved.
        self.assertTrue(all(provider.calls[c]["state"] in ("hangup", "active", "answered")
                            for c in provider.calls))

    def test_do_not_disturb_rejects(self):
        agent = TelephoneAgent(provider=LoopbackCallProvider())
        s = agent.on_incoming("c1", "x", DO_NOT_DISTURB)
        self.assertEqual(s.state, REJECTED)

    def test_recording_needs_consent(self):
        provider = LoopbackCallProvider()
        agent = TelephoneAgent(provider=provider)
        call_id = provider.incoming("x")
        s = agent.on_incoming(call_id, "x", MANUAL_ANSWER)
        agent.answer(s)
        with self.assertRaises(PermissionError):
            agent.run_exchange(s, record=True)

    def test_base_provider_has_no_pstn(self):
        from comms.telephone import CallProvider
        with self.assertRaises(NotImplementedError):
            CallProvider().place_call("+10000000000")


class AdapterBackendTests(unittest.TestCase):
    def test_email_draft_creates_artifact(self):
        import tempfile
        from tools.artifacts import ArtifactRegistry
        from tools.cat_comms import EmailAdapter
        with tempfile.TemporaryDirectory() as ws:
            adapter = EmailAdapter(
                {"workspace": ws, "artifacts": ArtifactRegistry()}, "email.compose")
            self.assertTrue(adapter.probe()["available"])
            out = adapter.execute({"to": "a@example.com", "subject": "hi", "body": "x"})
            self.assertTrue(out.get("ok"), out)
            import os
            self.assertTrue(os.path.exists(out["draft_ref"]))

    def test_email_send_refuses_without_provider(self):
        from tools.cat_comms import EmailAdapter
        out = EmailAdapter({}, "email.send").execute({"draft_ref": "x"})
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("status"), "PROVIDER_REQUIRED")

    def test_telephone_adapter_local_ops(self):
        from tools.cat_comms import TelephoneAdapter
        ctx: dict = {}
        policy = TelephoneAdapter(ctx, "telephone.answer_policy")
        self.assertTrue(policy.execute({}).get("ok"))
        hangup = TelephoneAdapter(ctx, "telephone.hangup")
        call_id = ctx["telephone_provider"].incoming("mock")
        out = hangup.execute({"call_id": call_id})
        self.assertTrue(out.get("ok"))
        state = TelephoneAdapter(ctx, "telephone.call_state").execute({"call_id": call_id})
        self.assertEqual(state.get("state"), "hangup")


if __name__ == "__main__":
    unittest.main()
