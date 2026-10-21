"""The two model defects this file covers.

The first is the routing one. The role map declares a primary coder
that is not installed on this machine, and a fallback that is not
installed either, while a different coder is. A role whose model was
missing therefore failed outright, on a machine that had a suitable
model in the inventory, and the only way out was for the operator to
hand-write a fallback chain for every role.

The second is the think one. A reasoning model that is left to think
puts its answer in the thinking field and leaves the content empty. The
Bridge then has nothing to act on, the run fails, and the error says
"empty chat response" without saying why. The runtime knows which
models can think, and the Bridge asks those to answer directly.

Both fixes have to be checkable without a model runtime, so the tests
here use a stub for the provider's discovery and a stub for the
transport.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from providers import OllamaProvider, ProviderError
from routing import RoleRouter


class _StubCaps:
    def __init__(self, reasoning: bool) -> None:
        self.reasoning = reasoning


class _StubV2:
    """Just enough of the canonical transport for these tests."""

    def __init__(self, models=None, reasoning=False, answer="hello",
                 thinking=""):
        self._models = list(models or [])
        self._reasoning = reasoning
        self._answer = answer
        self._thinking = thinking
        self.calls: list[dict] = []

    def list_models(self):
        return list(self._models)

    def discover(self, model: str):
        return _StubCaps(self._reasoning)

    def chat(self, model, messages, temperature=None, num_predict=None,
             think=None):
        self.calls.append({"model": model, "think": think,
                           "num_predict": num_predict})
        return {"model": model, "provider": "ollama",
                "content": self._answer, "thinking": self._thinking}


def _provider(stub: _StubV2, model: str = "m") -> OllamaProvider:
    provider = OllamaProvider(model=model)
    provider._v2 = stub
    return provider


class RoleCandidateTests(unittest.TestCase):
    def test_the_configured_model_comes_first(self):
        router = RoleRouter("qwen2.5-coder:3b-instruct-q4_K_M")
        for role in ("planner", "coder", "reviewer", "general"):
            self.assertEqual(router.candidates_for(role)[0],
                             router.model_for(role), role)

    def test_the_candidates_are_the_declared_role_map(self):
        from models.model_roles import ROLE_CANDIDATES

        router = RoleRouter("qwen2.5-coder:3b-instruct-q4_K_M")
        for role, declared in ROLE_CANDIDATES.items():
            candidates = router.candidates_for(role)
            for name in declared:
                self.assertIn(name, candidates, role)

    def test_a_candidate_is_not_repeated(self):
        router = RoleRouter("qwen3:1.7b")
        for role in ("planner", "coder", "reviewer", "general"):
            candidates = router.candidates_for(role)
            self.assertEqual(len(candidates), len(set(candidates)), role)

    def test_the_declared_coder_is_the_first_declared_choice_for_the_coder(self):
        from models.model_roles import MINIMUM_MODEL_COVERAGE

        router = RoleRouter("something-else")
        candidates = router.candidates_for("coder")
        # The configured model is always tried first, because that is
        # what the operator asked for. The declared primary coder is the
        # first of the DECLARED choices, which is what the order means.
        self.assertEqual(candidates[0], "something-else")
        self.assertEqual(candidates[1],
                         MINIMUM_MODEL_COVERAGE["primary_coder"])

    def test_a_model_outside_the_declaration_is_never_substituted(self):
        """An unnamed model is the operator's specific choice.

        The role map declares which models may serve a role, in order.
        A model that is not on that list was named for a reason, and the
        Bridge does not quietly run something else in its place: it
        surfaces that the model is not there.
        """
        from models.model_roles import ROLE_CANDIDATES

        router = RoleRouter("ghost-model-xyz")
        for role in ("planner", "coder", "reviewer", "general"):
            self.assertNotIn("ghost-model-xyz",
                             ROLE_CANDIDATES.get(role, []), role)
            self.assertNotIn("ghost-model-xyz",
                             router.declared_candidates(role), role)

    def test_a_declared_model_may_be_substituted_by_a_declared_one(self):
        from models.model_roles import MINIMUM_MODEL_COVERAGE

        declared = MINIMUM_MODEL_COVERAGE["primary_coder"]
        router = RoleRouter(declared)
        self.assertIn(declared, router.declared_candidates("coder"))
        self.assertIn(MINIMUM_MODEL_COVERAGE["fast_coder"],
                      router.declared_candidates("coder"))


class ThinkControlTests(unittest.TestCase):
    def test_a_model_that_can_think_is_asked_to_answer(self):
        stub = _StubV2(reasoning=True, answer="the answer")
        provider = _provider(stub)
        text = provider.chat([{"role": "user", "content": "go"}],
                              think=False)
        self.assertEqual(text, "the answer")
        self.assertIs(stub.calls[0]["think"], False)

    def test_a_model_that_cannot_think_is_never_sent_the_flag(self):
        stub = _StubV2(reasoning=False, answer="the answer")
        provider = _provider(stub)
        provider.chat([{"role": "user", "content": "go"}], think=None)
        self.assertIsNone(stub.calls[0]["think"])

    def test_the_think_support_is_discovered_from_the_runtime(self):
        self.assertTrue(_provider(_StubV2(reasoning=True))
                        .supports_think_control())
        self.assertFalse(_provider(_StubV2(reasoning=False))
                         .supports_think_control())

    def test_a_discovery_failure_does_not_claim_think_support(self):
        provider = OllamaProvider(model="m")

        class Broken:
            def discover(self, model):
                raise RuntimeError("the runtime is not reachable")

        provider._v2 = Broken()
        self.assertFalse(provider.supports_think_control())

    def test_an_answer_that_is_only_thinking_is_reported_honestly(self):
        stub = _StubV2(reasoning=True, answer="", thinking="x" * 900)
        provider = _provider(stub)
        with self.assertRaises(ProviderError) as caught:
            provider.chat([{"role": "user", "content": "go"}], think=False)
        message = str(caught.exception)
        self.assertIn("thinking", message)
        self.assertIn("900", message)
        # The old message was "empty chat response" and the whole dict,
        # which hid the cause and dumped the reasoning into the error.
        self.assertNotIn("empty chat response", message)

    def test_an_empty_answer_with_no_reasoning_is_still_an_empty_answer(self):
        stub = _StubV2(reasoning=False, answer="", thinking="")
        provider = _provider(stub)
        with self.assertRaises(ProviderError) as caught:
            provider.chat([{"role": "user", "content": "go"}])
        self.assertIn("empty chat response", str(caught.exception))


class ModelInventoryTests(unittest.TestCase):
    def test_the_provider_asks_the_runtime_for_the_models(self):
        stub = _StubV2(models=["a", "b"])
        self.assertEqual(_provider(stub).list_models(), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
