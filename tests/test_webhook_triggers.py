"""Webhook trigger ingestion tests (P21, REQ-webhook-triggers)."""
import json
import unittest

import webhook_triggers
from webhook_triggers import (
    BadSignature,
    DisallowedEventType,
    DuplicateEvent,
    MalformedEvent,
    OversizeEvent,
    SourcePolicy,
    StaleEvent,
    UnknownSource,
    WebhookIngestor,
    sign_body,
)

SECRET = b"test-secret-please-ignore"
NOW = 1_750_000_000_000


def policy(**over):
    base = {
        "source_id": "ci",
        "allowed_event_types": ("BUILD.FINISHED",),
        "secret_ref": "vault://webhooks/ci",
        "max_age_s": 300,
        "max_bytes": 1024,
        "allowed_payload_fields": ("status", "branch"),
    }
    base.update(over)
    return SourcePolicy(**base)


def ingestor(policies=None, now=NOW):
    return WebhookIngestor(
        policies or [policy()],
        resolve_secret=lambda ref: SECRET if ref == "vault://webhooks/ci" else b"",
        now_ms=lambda: now,
    )


def body(**fields):
    base = {"status": "ok", "branch": "main", "internal": "drop-me"}
    base.update(fields)
    return json.dumps(base).encode()


def headers(secret=SECRET, payload=b""):
    return {"X-Signature-Sha256": sign_body(secret, payload)}


class TestIngestion(unittest.TestCase):
    def test_valid_signed_webhook_normalizes(self):
        ing = ingestor()
        payload = body()
        event = ing.ingest("ci", payload, headers(SECRET, payload), "e1", "BUILD.FINISHED", NOW - 1000)
        self.assertEqual(event.event_id, "e1")
        self.assertEqual(event.source, "webhook:ci")
        self.assertEqual(event.payload, {"status": "ok", "branch": "main"})
        self.assertEqual(event.provenance, "webhook:ci:verified")

    def test_header_name_case_insensitive(self):
        ing = ingestor()
        payload = body()
        event = ing.ingest(
            "ci", payload, {"x-signature-SHA256": sign_body(SECRET, payload)},
            "e2", "BUILD.FINISHED", NOW - 1000,
        )
        self.assertEqual(event.event_id, "e2")

    def test_unknown_source_rejected(self):
        ing = ingestor()
        with self.assertRaises(UnknownSource):
            ing.ingest("stranger", b"{}", {}, "e", "BUILD.FINISHED", NOW)
        self.assertEqual(ing.sources(), ["ci"])

    def test_bad_and_missing_signatures_rejected(self):
        ing = ingestor()
        payload = body()
        with self.assertRaises(BadSignature):
            ing.ingest("ci", payload, headers(b"wrong", payload), "e3", "BUILD.FINISHED", NOW)
        with self.assertRaises(BadSignature):
            ing.ingest("ci", payload, {}, "e4", "BUILD.FINISHED", NOW)
        with self.assertRaises(BadSignature):
            ing.ingest("ci", b'{"status":"tampered"}', headers(SECRET, payload), "e5", "BUILD.FINISHED", NOW)

    def test_stale_future_and_duplicate_rejected(self):
        ing = ingestor()
        payload = body()
        with self.assertRaises(StaleEvent):
            ing.ingest("ci", payload, headers(SECRET, payload), "old", "BUILD.FINISHED", NOW - 301_000)
        with self.assertRaises(StaleEvent):
            ing.ingest("ci", payload, headers(SECRET, payload), "future", "BUILD.FINISHED", NOW + 61_000)
        ing.ingest("ci", payload, headers(SECRET, payload), "once", "BUILD.FINISHED", NOW)
        with self.assertRaises(DuplicateEvent):
            ing.ingest("ci", payload, headers(SECRET, payload), "once", "BUILD.FINISHED", NOW)

    def test_size_type_and_shape_guards(self):
        ing = ingestor()
        with self.assertRaises(OversizeEvent):
            ing.ingest("ci", b"x" * 1025, {}, "big", "BUILD.FINISHED", NOW)
        with self.assertRaises(DisallowedEventType):
            ing.ingest("ci", b"{}", {}, "t", "DEPLOY.NOW", NOW)
        with self.assertRaises(MalformedEvent):
            ing.ingest("ci", b"not json", headers(SECRET, b"not json"), "m", "BUILD.FINISHED", NOW)
        with self.assertRaises(MalformedEvent):
            arr = b"[1,2]"
            ing.ingest("ci", arr, headers(SECRET, arr), "a", "BUILD.FINISHED", NOW)

    def test_unsigned_source_when_policy_allows(self):
        ing = WebhookIngestor([policy(require_signature=False)], now_ms=lambda: NOW)
        event = ing.ingest("ci", body(), {}, "open", "BUILD.FINISHED", NOW)
        self.assertEqual(event.event_id, "open")

    def test_secrets_never_echoed(self):
        ing = ingestor()
        payload = body()
        try:
            ing.ingest("ci", payload, headers(b"wrong", payload), "s", "BUILD.FINISHED", NOW)
            self.fail("expected BadSignature")
        except BadSignature as exc:
            self.assertNotIn("test-secret", str(exc))
            self.assertNotIn(SECRET.decode(), str(exc))
        import inspect

        source = inspect.getsource(webhook_triggers)
        self.assertNotIn("test-secret", source)


if __name__ == "__main__":
    unittest.main()
