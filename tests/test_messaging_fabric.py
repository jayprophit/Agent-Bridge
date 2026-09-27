"""Multichannel messaging fabric tests. No real sends, no network, no providers."""
import unittest

from comms.fabric import (
    AuthorizationRequired,
    ChannelProfile,
    ConsentLedger,
    ConsentRequired,
    FabricError,
    LoopbackMessageProvider,
    MessageConflict,
    MessageProvider,
    ProviderRequired,
    UnknownChannel,
    UnsupportedCapability,
    check_capabilities,
    dispatch_routed,
    normalize_envelope,
    normalize_inbound,
    route_message,
)


def profile(**over):
    base = {
        "channel_id": "chan-mail",
        "kind": "email",
        "direction": "both",
        "capabilities": {"text": True, "attachments": False, "threads": True, "receipts": False},
        "provider_id": "loopback-mock",
        "status": "AVAILABLE",
        "provenance": "fixture",
    }
    base.update(over)
    return ChannelProfile(**base)


def envelope(**over):
    base = {
        "message_id": "msg-1",
        "channel_id": "chan-mail",
        "direction": "outbound",
        "sender_ref": "agent:default",
        "recipient_refs": ["user:ana"],
        "content": {"text": "hello"},
        "authored_at": "2026-09-27T10:00:00Z",
        "received_at": "2026-09-27T10:00:00Z",
        "observed_at": "2026-09-27T10:00:01Z",
        "provenance": "fixture",
    }
    base.update(over)
    return base


class ChannelProfileTests(unittest.TestCase):
    def test_registers_only_kinds_with_adapters(self):
        for kind in ("email", "telephone", "webhook"):
            self.assertEqual(profile(kind=kind).kind, kind)
        with self.assertRaises(FabricError):
            profile(kind="slack")

    def test_capabilities_must_be_explicit_booleans(self):
        with self.assertRaises(FabricError):
            profile(capabilities={"text": "yes"})
        with self.assertRaises(FabricError):
            profile(direction="sideways")

    def test_configured_is_not_available(self):
        configured = profile(status="CONFIGURED")
        with self.assertRaises(UnknownChannel):
            route_message({"chan-mail": configured}, envelope(), "chan-mail")


class EnvelopeTests(unittest.TestCase):
    def test_normalizes_and_sorts(self):
        out = normalize_envelope(envelope(recipient_refs=["user:z", "user:a"]))
        self.assertEqual(out["recipient_refs"], ["user:a", "user:z"])
        self.assertEqual(out["direction"], "outbound")

    def test_direction_is_explicit_never_inferred(self):
        bad = envelope()
        del bad["direction"]
        with self.assertRaises(FabricError):
            normalize_envelope(bad)

    def test_unknown_fields_rejected_not_dropped(self):
        with self.assertRaises(FabricError):
            normalize_envelope({**envelope(), "urgency": 9})

    def test_security_fields_rejected_first(self):
        with self.assertRaises(FabricError):
            normalize_envelope({**envelope(), "api_key": "sk-x", "extra": 1})
        with self.assertRaises(FabricError):
            normalize_envelope({**envelope(), "authorized": True})
        with self.assertRaises(FabricError):
            normalize_envelope({**envelope(), "persona": "helper"})

    def test_attachments_are_refs_and_sorted(self):
        out = normalize_envelope(envelope(content={"text": "hi", "attachment_refs": ["b", "a"]}))
        self.assertEqual(out["content"]["attachment_refs"], ["a", "b"])

    def test_thread_and_reply_preserved_when_present(self):
        out = normalize_envelope(envelope(thread_ref="thread-1", reply_to="msg-0"))
        self.assertEqual(out["thread_ref"], "thread-1")
        self.assertEqual(out["reply_to"], "msg-0")


class InboundTests(unittest.TestCase):
    def test_email_inbound_maps_known_fields_and_preserves_rest(self):
        out = normalize_inbound("email", {
            "sender": "ana@example.com",
            "to": "bridge@example.com",
            "subject": "hello",
            "body": "hi there",
            "message_id": "ext-1",
            "date": "2026-09-27T09:00:00Z",
            "x_custom": "kept",
        }, "chan-mail", "2026-09-27T10:00:00Z")
        self.assertEqual(out["direction"], "inbound")
        self.assertEqual(out["sender_ref"], "ana@example.com")
        self.assertEqual(out["content"]["text"], "hi there")
        # Subject is channel semantics, not a thread: preserved, not promoted.
        self.assertEqual(out["channel_data"]["subject"], "hello")
        self.assertEqual(out["channel_data"]["x_custom"], "kept")
        self.assertNotIn("thread_ref", out)

    def test_sequential_messages_do_not_share_a_thread(self):
        first = normalize_inbound("webhook", {"source": "s", "event_id": "e1", "text": "one",
                                              "received_at": "2026-09-27T10:00:00Z"},
                                  "chan-hook", "2026-09-27T10:00:01Z")
        second = normalize_inbound("webhook", {"source": "s", "event_id": "e2", "text": "two",
                                               "received_at": "2026-09-27T10:00:02Z"},
                                   "chan-hook", "2026-09-27T10:00:03Z")
        self.assertNotIn("thread_ref", first)
        self.assertNotIn("thread_ref", second)

    def test_contentless_event_belongs_to_event_layer_not_messaging(self):
        with self.assertRaises(FabricError):
            normalize_inbound("webhook", {"source": "s", "event_id": "e1"},
                              "chan-hook", "2026-09-27T10:00:01Z")

    def test_inbound_without_text_is_rejected(self):
        with self.assertRaises(FabricError):
            normalize_inbound("webhook", {"source": "s", "event_id": "e1"}, "chan-hook", "2026-09-27T10:00:01Z")

    def test_unknown_kind_rejected(self):
        with self.assertRaises(FabricError):
            normalize_inbound("slack", {}, "chan-x", "2026-09-27T10:00:01Z")


class RoutingTests(unittest.TestCase):
    def test_explicit_selection_routes(self):
        routed = route_message({"chan-mail": profile()}, envelope(), "chan-mail")
        self.assertEqual(routed["channel_id"], "chan-mail")
        self.assertEqual(routed["provider_id"], "loopback-mock")
        self.assertEqual(routed["checks"], ["channel-known", "direction-ok", "capabilities-ok", "consent-ok", "authorization-ok"])

    def test_unknown_channel_rejected(self):
        with self.assertRaises(UnknownChannel):
            route_message({}, envelope(), "chan-ghost")

    def test_direction_mismatch_rejected(self):
        only_in = profile(channel_id="chan-in", direction="inbound")
        with self.assertRaises(UnsupportedCapability):
            route_message({"chan-in": only_in}, envelope(direction="outbound"), "chan-in")

    def test_unsupported_capability_refused_never_stripped(self):
        with self.assertRaises(UnsupportedCapability):
            route_message({"chan-mail": profile()}, envelope(), "chan-mail",
                            requested_capabilities={"attachments": True})

    def test_consent_gate(self):
        gated = profile(channel_id="chan-voice", kind="telephone", requires_consent=True)
        ledger = ConsentLedger()
        with self.assertRaises(ConsentRequired):
            route_message({"chan-voice": gated}, envelope(channel_id="chan-voice"), "chan-voice", consent=ledger)
        ledger.deny("chan-voice", "agent:default", "fixture", "2026-09-27T10:00:00Z")
        with self.assertRaises(ConsentRequired):
            route_message({"chan-voice": gated}, envelope(channel_id="chan-voice"), "chan-voice", consent=ledger)
        ledger.grant("chan-voice", "agent:default", "fixture", "2026-09-27T10:00:00Z")
        routed = route_message({"chan-voice": gated}, envelope(channel_id="chan-voice"), "chan-voice", consent=ledger)
        self.assertEqual(routed["channel_id"], "chan-voice")

    def test_consent_unknown_without_ledger(self):
        gated = profile(channel_id="chan-voice", kind="telephone", requires_consent=True)
        with self.assertRaises(ConsentRequired):
            route_message({"chan-voice": gated}, envelope(channel_id="chan-voice"), "chan-voice")

    def test_authorization_ref_required_never_decided(self):
        locked = profile(channel_id="chan-hi", requires_authorization=True)
        with self.assertRaises(AuthorizationRequired):
            route_message({"chan-hi": locked}, envelope(channel_id="chan-hi"), "chan-hi")
        routed = route_message({"chan-hi": locked}, envelope(channel_id="chan-hi"), "chan-hi",
                                 authorization_ref="p25:decision-7")
        self.assertEqual(routed["channel_id"], "chan-hi")


class ConsentLedgerTests(unittest.TestCase):
    def test_absent_is_unknown_never_no(self):
        ledger = ConsentLedger()
        self.assertEqual(ledger.check("chan-x", "someone"), "UNKNOWN")

    def test_grant_and_deny_roundtrip(self):
        ledger = ConsentLedger()
        ledger.grant("c", "s", "fixture", "2026-09-27T10:00:00Z")
        self.assertEqual(ledger.check("c", "s"), "GRANTED")
        ledger.deny("c", "s", "fixture", "2026-09-27T10:00:01Z")
        self.assertEqual(ledger.check("c", "s"), "DENIED")


class ProviderSeamTests(unittest.TestCase):
    def test_loopback_records_without_network(self):
        provider = LoopbackMessageProvider()
        routed = route_message({"chan-mail": profile()}, envelope(), "chan-mail")
        result = dispatch_routed(provider, routed, {})
        self.assertTrue(result["ok"])
        self.assertTrue(result["mock"])
        self.assertFalse(result["duplicate"])
        self.assertEqual(len(provider.dispatched), 1)
        self.assertEqual(provider.dispatched[0]["message_id"], "msg-1")

    def test_real_provider_stays_provider_required(self):
        routed = route_message({"chan-mail": profile()}, envelope(), "chan-mail")
        with self.assertRaises(ProviderRequired):
            dispatch_routed(MessageProvider(), routed, {})

    def test_identical_redispatch_idempotent_conflicting_refused(self):
        provider = LoopbackMessageProvider()
        routed = route_message({"chan-mail": profile()}, envelope(), "chan-mail")
        ledger: dict = {}
        first = dispatch_routed(provider, routed, ledger)
        self.assertFalse(first["duplicate"])
        second = dispatch_routed(provider, routed, ledger)
        self.assertTrue(second["duplicate"])
        self.assertEqual(len(provider.dispatched), 1)
        altered = dict(routed)
        altered["envelope"] = {**routed["envelope"], "content": {"text": "different"}}
        with self.assertRaises(MessageConflict):
            dispatch_routed(provider, altered, ledger)


class CapabilityCheckTests(unittest.TestCase):
    def test_unrequested_capabilities_ignored_supported_required(self):
        check_capabilities(profile(), {"text": True})
        with self.assertRaises(UnsupportedCapability):
            check_capabilities(profile(), {"receipts": True})


class DeterminismTests(unittest.TestCase):
    def test_routing_deterministic_from_scrambled_metadata(self):
        base = envelope()
        variants = [
            dict(base, provenance="a"),
            dict(base, provenance="b"),
        ]
        first = route_message({"chan-mail": profile()}, variants[0], "chan-mail")
        second = route_message({"chan-mail": profile()}, variants[1], "chan-mail")
        self.assertEqual(first["channel_id"], second["channel_id"])
        self.assertEqual(first["checks"], second["checks"])


if __name__ == "__main__":
    unittest.main()
