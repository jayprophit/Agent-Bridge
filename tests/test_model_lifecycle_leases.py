"""Provider-level model lifecycle tests (§3–§10 of the lifecycle directive).

WHY THESE TESTS EXIST

The residency leak was fixed once at `local_team_executor.py` and then came
back through every other Ollama call site, because residency is a property of
the runtime and the ownership decision belongs on the provider. These tests
pin the provider boundary itself, so a new call site cannot reintroduce the
leak without a test failing.

WHAT IS DETERMINISTIC AND WHAT IS LIVE (§19)

Ownership, refcounting and policy routing are exercised against a fake
transport — deterministic, no network, no models loaded. Residency
confirmation against the real Ollama runtime is a separate, bounded live
test that skips cleanly when Ollama is not reachable, because a test that
silently passes without the runtime proves nothing.

The fake transport records requests rather than answering them, so the tests
assert on what the provider WOULD send (keep_alive, unload calls) instead of
depending on a live runtime's timing.
"""

from __future__ import annotations

import unittest

from compute.ollama_provider_v2 import (
    DEFAULT_LEASE_POLICY,
    LeasePolicy,
    ModelLease,
    ModelOwnership,
    OllamaProviderV2,
)

MODEL = "llama3.2:1b-instruct-q4_K_M"
EMBEDDER = "nomic-embed-text:latest"


class FakeTransport:
    """Records requests; returns canned responses. No network (§19)."""

    def __init__(self, resident: list[str] | None = None):
        self.resident = set(resident or [])
        self.calls: list[tuple[str, dict]] = []

    def install(self, provider: OllamaProviderV2) -> OllamaProviderV2:
        provider._get = self._get  # type: ignore[method-assign]
        provider._capability_cache.clear()
        return provider

    def _get(self, path: str, payload: dict | None = None):
        payload = payload or {}
        self.calls.append((path, dict(payload)))

        if path == "/api/tags":
            return {"models": [{"name": MODEL}, {"name": EMBEDDER}]}
        if path == "/api/show":
            model = payload.get("model", "")
            if model == EMBEDDER:
                return {"capabilities": ["embedding"],
                        "model_info": {"bert.embedding_length": 768},
                        "details": {"family": "bert"}}
            return {"capabilities": ["completion", "tools"],
                    "thinking": {"values": [False], "default": False},
                    "model_info": {"llama.context_length": 131072},
                    "details": {"family": "llama", "parameter_size": "1.2B"}}
        if path == "/api/ps":
            return {"models": [{"name": m} for m in sorted(self.resident)]}
        if path == "/api/generate":
            model = payload.get("model", "")
            # Ollama's real behaviour: keep_alive=0 drops the model, and a
            # fresh load brings it resident. Modelling this is what lets the
            # ownership tests be deterministic instead of timing-dependent.
            if payload.get("keep_alive") == 0:
                self.resident.discard(model)
            else:
                self.resident.add(model)
            return {"response": "ok", "done": True,
                    "prompt_eval_count": 3, "eval_count": 1}
        if path == "/api/embeddings":
            return {"embedding": [0.1, 0.2, 0.3]}
        return {}

    # -- assertions helpers -------------------------------------------------
    def calls_to(self, path: str) -> list[dict]:
        return [p for pth, p in self.calls if pth == path]

    @property
    def unload_calls(self) -> list[dict]:
        return [p for p in self.calls_to("/api/generate")
                if p.get("keep_alive") == 0]


def make_provider(resident: list[str] | None = None,
                  **kwargs) -> tuple[OllamaProviderV2, FakeTransport]:
    fake = FakeTransport(resident)
    provider = fake.install(OllamaProviderV2(**kwargs))
    return provider, fake


# --------------------------------------------------------------------------
# A. ephemeral inference releases the model
# --------------------------------------------------------------------------
class EphemeralReleaseTests(unittest.TestCase):
    def test_ephemeral_infer_releases_model(self):
        provider, fake = make_provider()
        result = provider.infer(MODEL, "hi", policy=LeasePolicy.EPHEMERAL)
        self.assertEqual(result["response"], "ok")
        self.assertNotIn(MODEL, provider.resident_models(),
                         "EPHEMERAL inference left the model resident")
        self.assertTrue(any(p.get("model") == MODEL
                            for p in fake.unload_calls),
                        "no keep_alive=0 unload was issued")

    def test_session_infer_keeps_the_lease_open(self):
        """SESSION weights are meant to be warm for the next turn (§6).

        The lease deliberately outlives the call: dropping it per-request
        would make SESSION identical to EPHEMERAL and force a reload every
        turn. `release_all()` is the honest end of the session.
        """
        provider, fake = make_provider()
        provider.infer(MODEL, "hi", policy=LeasePolicy.SESSION)
        self.assertIn(MODEL, provider.resident_models())
        self.assertEqual([], fake.unload_calls,
                         "SESSION inference unloaded its own weights")
        self.assertTrue(any(l.active for l in provider._lease_records.values()),
                        "SESSION lease was dropped at end of call")

        provider.release_all()
        self.assertNotIn(MODEL, provider.resident_models(),
                         "release_all did not end the session")

    def test_session_failure_still_drops_the_lease(self):
        """A failed request has no session to keep warm (§9-H)."""
        provider, _ = make_provider()

        def boom(path, payload=None):
            if payload and payload.get("prompt") == "hi":
                raise RuntimeError("inference blew up")
            return {"models": []}

        provider._get = boom  # type: ignore[method-assign]
        with self.assertRaises(RuntimeError):
            provider.infer(MODEL, "hi", policy=LeasePolicy.SESSION)
        self.assertFalse(any(l.active
                             for l in provider._lease_records.values()),
                         "a failed SESSION request left its lease live")

    def test_ephemeral_policy_sends_keep_alive_zero(self):
        provider, fake = make_provider()
        provider.infer(MODEL, "hi", policy=LeasePolicy.EPHEMERAL)
        gens = [p for p in fake.calls_to("/api/generate")
                if p.get("prompt") == "hi"]
        self.assertEqual(gens[0].get("keep_alive"), 0,
                         "EPHEMERAL must send keep_alive=0 on the request itself")

    def test_lifecycle_metadata_is_reported(self):
        """§8 — non-secret lease metadata rides on the result."""
        provider, _ = make_provider()
        result = provider.infer(MODEL, "hi", policy=LeasePolicy.EPHEMERAL,
                                task_id="task-1", worker_id="worker-a")
        lifecycle = result["lifecycle"]
        self.assertEqual(lifecycle["policy"], "EPHEMERAL")
        self.assertEqual(lifecycle["task_id"], "task-1")
        self.assertEqual(lifecycle["worker_id"], "worker-a")
        self.assertEqual(lifecycle["model"], MODEL)


# --------------------------------------------------------------------------
# B. persistent/session inference retains the model intentionally
# --------------------------------------------------------------------------
class RetentionTests(unittest.TestCase):
    def test_session_policy_retains_model(self):
        provider, fake = make_provider()
        provider.infer(MODEL, "hi", policy=LeasePolicy.SESSION)
        self.assertIn(MODEL, provider.resident_models(),
                      "SESSION policy must NOT unload the model")
        gens = [p for p in fake.calls_to("/api/generate")
                if p.get("prompt") == "hi"]
        self.assertEqual(gens[0].get("keep_alive"), -1)

    def test_persistent_policy_is_never_auto_released(self):
        provider, _ = make_provider()
        lease = provider.acquire(MODEL, policy=LeasePolicy.PERSISTENT)
        outcome = provider.release(lease)
        self.assertTrue(outcome["released"])
        self.assertFalse(outcome["unloaded"],
                         "PERSISTENT must survive release")

    def test_default_policy_is_not_ephemeral(self):
        """The default must not silently unload production inference."""
        self.assertEqual(DEFAULT_LEASE_POLICY, LeasePolicy.SESSION)


# --------------------------------------------------------------------------
# C. two workers sharing one model do not unload it prematurely (§4)
# --------------------------------------------------------------------------
class SharedModelTests(unittest.TestCase):
    def test_second_lease_prevents_unload(self):
        provider, _ = make_provider()
        first = provider.acquire(MODEL, policy=LeasePolicy.SHORT_LIVED,
                                 worker_id="worker-a")
        second = provider.acquire(MODEL, policy=LeasePolicy.SHORT_LIVED,
                                  worker_id="worker-b")

        outcome = provider.release(first)
        self.assertTrue(outcome["released"])
        self.assertFalse(outcome["unloaded"],
                         "released a model another live worker still holds")
        self.assertEqual(provider.classify_ownership(MODEL),
                         ModelOwnership.SHARED)

    def test_final_lease_release_unloads_the_model(self):
        provider, _ = make_provider()
        first = provider.acquire(MODEL, policy=LeasePolicy.EPHEMERAL,
                                 worker_id="worker-a")
        second = provider.acquire(MODEL, policy=LeasePolicy.EPHEMERAL,
                                  worker_id="worker-b")
        provider.release(first)
        outcome = provider.release(second)
        self.assertTrue(outcome["unloaded"],
                        "final lease release must unload the model")
        self.assertNotIn(MODEL, provider.resident_models())

    def test_ownership_shared_while_lease_active(self):
        provider, _ = make_provider()
        provider.acquire(MODEL)
        provider.acquire(MODEL)
        self.assertEqual(provider.classify_ownership(MODEL),
                         ModelOwnership.SHARED)


# --------------------------------------------------------------------------
# D. final lease release unloads (single lease path)
# --------------------------------------------------------------------------
class FinalReleaseTests(unittest.TestCase):
    def test_single_lease_release_unloads(self):
        provider, _ = make_provider()
        lease = provider.acquire(MODEL, policy=LeasePolicy.EPHEMERAL)
        outcome = provider.release(lease)
        self.assertTrue(outcome["unloaded"])
        self.assertTrue(lease.release_confirmed)

    def test_double_release_is_idempotent(self):
        provider, _ = make_provider()
        lease = provider.acquire(MODEL, policy=LeasePolicy.EPHEMERAL)
        provider.release(lease)
        again = provider.release(lease)
        self.assertFalse(again["released"],
                         "releasing the same lease twice must be a no-op")


# --------------------------------------------------------------------------
# E. pre-existing model is not killed (§5)
# --------------------------------------------------------------------------
class PreexistingSafetyTests(unittest.TestCase):
    def test_preexisting_model_is_never_unloaded(self):
        """Hermes' own llama-server is resident before we ever ask (§5)."""
        provider, fake = make_provider(resident=[MODEL])
        provider.capture_baseline()          # now it is PREEXISTING
        self.assertEqual(provider.classify_ownership(MODEL),
                         ModelOwnership.PREEXISTING)

        lease = provider.acquire(MODEL, policy=LeasePolicy.EPHEMERAL)
        outcome = provider.release(lease)
        self.assertTrue(outcome["released"])
        self.assertFalse(outcome["unloaded"],
                         "a PREEXISTING model must never be unloaded")
        self.assertEqual(outcome["reason"], "ownership=PREEXISTING")
        self.assertIn(MODEL, provider.resident_models(),
                      "pre-existing model was actually dropped")

    def test_unknown_ownership_fails_safe(self):
        """Resident, not at baseline, no lease of ours → leave it alone."""
        provider, _ = make_provider(resident=["someone-elses-model"])
        provider.capture_baseline()
        # Another component loaded this AFTER our baseline: it is resident,
        # but no lease of ours explains it, so we must not claim it.
        provider._baseline_resident = set()
        provider.resident_models = lambda: ["someone-elses-model"]  # type: ignore[method-assign]
        self.assertEqual(provider.classify_ownership("someone-elses-model"),
                         ModelOwnership.UNKNOWN)

        lease = ModelLease(lease_id="l1", model="someone-elses-model",
                           owner_id="aetherius",
                           policy=LeasePolicy.EPHEMERAL)
        provider._lease_records["l1"] = lease
        provider._leases["someone-elses-model"] = ["l1"]
        outcome = provider.release(lease)
        self.assertFalse(outcome["unloaded"],
                         "UNKNOWN ownership must fail safe, not unload")

    def test_baseline_is_captured_once(self):
        provider, _ = make_provider(resident=[MODEL])
        provider.capture_baseline()
        first = set(provider._baseline_resident)
        provider.capture_baseline()
        self.assertEqual(first, provider._baseline_resident,
                         "baseline must not drift after capture")


# --------------------------------------------------------------------------
# F/G/H. failure, timeout and exception paths release the owned model
# --------------------------------------------------------------------------
class FailurePathTests(unittest.TestCase):
    def test_exception_path_releases_model(self):
        provider, fake = make_provider()

        def boom(path, payload=None):
            fake.calls.append((path, dict(payload or {})))
            if payload and payload.get("prompt") == "hi":
                raise RuntimeError("inference blew up")
            return {"models": []}

        provider._get = boom  # type: ignore[method-assign]
        with self.assertRaises(RuntimeError):
            provider.infer(MODEL, "hi", policy=LeasePolicy.EPHEMERAL)

        self.assertFalse(any(l.active for l in provider._lease_records.values()),
                         "an exception left a live lease behind")
        self.assertTrue(any(p.get("keep_alive") == 0
                            for p in fake.unload_calls),
                        "exception path issued no unload")

    def test_unsupported_capability_does_not_leave_a_lease(self):
        """Capability gating raises BEFORE the lease is taken."""
        provider, _ = make_provider()
        with self.assertRaises(Exception):
            provider.infer(EMBEDDER, "hi", tools=[{"name": "t"}])
        self.assertEqual(provider._lease_records, {},
                         "a rejected request must not hold a lease")

    def test_timeout_path_releases(self):
        """A stuck unload still releases the lease, just flags it (§10).

        The lease is dropped and the unload IS attempted — only the
        confirmation times out. A stuck runtime must not strand the lease.

        The stub is stateful on purpose. `classify_ownership` consults
        `_leased_models` before probing residency, so a model we leased is
        attributed to us without a network call; the poll below is what must
        keep seeing it resident to represent a runtime that never drops the
        weights.
        """
        provider, _ = make_provider()
        lease = provider.acquire(MODEL, policy=LeasePolicy.EPHEMERAL)
        # A runtime that never drops the weights: every residency sample
        # after this reports the model still resident, so the confirmation
        # poll runs to its deadline instead of passing.
        provider.resident_models = lambda: [MODEL]  # type: ignore[method-assign]
        outcome = provider.release(lease, timeout=0.6)
        self.assertTrue(outcome["released"], "lease was not released")
        self.assertFalse(outcome["unloaded"])
        self.assertFalse(lease.active, "lease stayed active on a stuck unload")
        self.assertTrue(lease.resident_after_call,
                        "a genuinely stuck unload must be reported, not hidden")
        self.assertIn("not confirmed", outcome["reason"])


# --------------------------------------------------------------------------
# I. direct provider inference cannot bypass lifecycle policy
# --------------------------------------------------------------------------
class BypassTests(unittest.TestCase):
    def test_infer_always_sends_keep_alive(self):
        """Even a caller that passes nothing gets an explicit residency."""
        provider, fake = make_provider()
        provider.infer(MODEL, "hi")
        gens = [p for p in fake.calls_to("/api/generate")
                if p.get("prompt") == "hi"]
        self.assertIn("keep_alive", gens[0],
                      "inference went out without a keep_alive decision")

    def test_embed_is_leased_too(self):
        provider, fake = make_provider()
        provider.embed(EMBEDDER, "hello", policy=LeasePolicy.EPHEMERAL)
        self.assertNotIn(EMBEDDER, provider.resident_models(),
                         "embed() left the embedder resident")
        embeds = fake.calls_to("/api/embeddings")
        self.assertEqual(embeds[0].get("keep_alive"), 0)

    def test_release_all_clears_every_lease(self):
        provider, _ = make_provider()
        provider.acquire(MODEL)
        provider.acquire(EMBEDDER, policy=LeasePolicy.EPHEMERAL)
        outcomes = provider.release_all()
        self.assertEqual(len(outcomes), 2)
        self.assertFalse(any(l.active
                             for l in provider._lease_records.values()),
                         "release_all left active leases")

    def test_release_all_sweeps_retained_session_weights(self):
        """A SESSION call ends its lease but keeps the weights (§6).

        `infer()` releases its own lease, so by the time release_all() runs
        there is nothing active to release — but the weights are still
        resident. Declaring the session over must actually free them, or
        `release_models()` becomes a no-op that looks like success (§12).
        """
        provider, _ = make_provider()
        provider.infer(MODEL, "hi", policy=LeasePolicy.SESSION)
        self.assertIn(MODEL, provider.resident_models(),
                      "SESSION must retain the model — that is the point")

        outcomes = provider.release_all()
        self.assertTrue(any(o.get("unloaded") for o in outcomes),
                        "release_all did not free retained session weights")
        self.assertNotIn(MODEL, provider.resident_models())

    def test_release_all_never_touches_preexisting_weights(self):
        """The sweep must honour §5 even though it bypasses the lease path."""
        provider, _ = make_provider(resident=[MODEL, "hermes-own-model"])
        provider.capture_baseline()
        # Only our own model gets leased; the other stays PREEXISTING.
        provider.acquire(MODEL, policy=LeasePolicy.EPHEMERAL)
        provider.release_all()
        self.assertIn("hermes-own-model", provider.resident_models(),
                      "release_all evicted a PREEXISTING model (§5)")

    def test_own_weights_are_not_mistaken_for_unknown(self):
        """REGRESSION: at release time refcount is already zero.

        A model we loaded is resident with no live lease. Classifying that
        as UNKNOWN would make the release path refuse to unload its own
        weights — a leak disguised as caution.
        """
        provider, _ = make_provider()
        lease = provider.acquire(MODEL, policy=LeasePolicy.EPHEMERAL)
        provider._leases.pop(MODEL, None)   # refcount drops to zero
        self.assertEqual(provider.classify_ownership(MODEL),
                         ModelOwnership.AETHERIUS_LOADED,
                         "our own resident weights were classified UNKNOWN")
        self.assertTrue(provider.release(lease)["unloaded"])


# --------------------------------------------------------------------------
# J. tests leave no Aetherius-owned stale model servers
# --------------------------------------------------------------------------
class HygieneTests(unittest.TestCase):
    def test_lifecycle_report_is_secret_free(self):
        """§5 — trace/lease metadata must not carry secrets."""
        provider, _ = make_provider()
        provider.acquire(MODEL, task_id="t", worker_id="w")
        provider.release_all()
        report = provider.lifecycle_report()
        blob = repr(report).lower()
        for banned in ("password", "api_key", "token", "secret", "master"):
            self.assertNotIn(banned, blob,
                             f"lifecycle report leaked '{banned}'")

    def test_no_lease_survives_a_released_run(self):
        provider, _ = make_provider()
        provider.infer(MODEL, "a", policy=LeasePolicy.EPHEMERAL)
        provider.infer(MODEL, "b", policy=LeasePolicy.EPHEMERAL)
        self.assertEqual(provider._leases, {},
                         "released runs still hold refcounts")
        self.assertEqual(provider.resident_models(), [],
                         "released runs left resident models")


# --------------------------------------------------------------------------
# Bounded live proof (§19) — real runtime, skips cleanly when absent
# --------------------------------------------------------------------------
def _live() -> bool:
    try:
        return OllamaProviderV2(timeout=3.0).is_available()
    except Exception:
        return False


@unittest.skipUnless(_live(), "Ollama runtime not reachable")
class LiveLifecycleTests(unittest.TestCase):
    """Proves the lease behaviour against the real runtime, not a fake.

    Bounded: one small model, EPHEMERAL policy, so the run cannot leak.
    """

    def setUp(self):
        self.provider = OllamaProviderV2()
        self.installed = self.provider.list_models()
        for candidate in ("llama3.2:1b-instruct-q4_K_M", "qwen3:0.6b"):
            if candidate in self.installed:
                self.model = candidate
                break
        else:
            self.skipTest("no small text model installed")
        # Whatever is resident now is not ours (§5).
        self.baseline = self.provider.capture_baseline()

    def tearDown(self):
        self.provider.release_all()

    def test_live_ephemeral_inference_releases(self):
        result = self.provider.infer(self.model, "Reply with exactly: OK",
                                     max_tokens=8,
                                     policy=LeasePolicy.EPHEMERAL)
        self.assertTrue(result["done"])
        self.assertNotIn(self.model, self.provider.resident_models(),
                         "live EPHEMERAL inference leaked the model")

    def test_live_preexisting_model_survives_a_run(self):
        """The runtime's own resident models must not be evicted by us."""
        if not self.baseline:
            self.skipTest("no pre-existing resident model to protect")
        lease = self.provider.acquire(
            sorted(self.baseline)[0], policy=LeasePolicy.EPHEMERAL)
        outcome = self.provider.release(lease)
        self.assertFalse(outcome["unloaded"])
        for model in self.baseline:
            self.assertIn(model, self.provider.resident_models(),
                          f"pre-existing model {model} was evicted")


if __name__ == "__main__":
    unittest.main(verbosity=2)
