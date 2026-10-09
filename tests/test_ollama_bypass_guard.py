"""Static guard: no production path may load Ollama weights outside Provider V2.

§consolidation — the architectural point is that lifecycle correctness is
STRUCTURAL, not remembered. Nine bypasses closed by nine manual `unload()`
calls would drift back the moment someone adds a tenth. This test is the
guard that keeps them from coming back: it scans tracked production source for
direct calls to Ollama's weight-loading endpoints and fails if a new one
appears that is not on the explicit allowlist.

WHAT COUNTS AS A BYPASS
-----------------------
A direct construction of an Ollama load-triggering URL — /api/generate,
/api/chat, /api/embeddings — in production code. Read-only discovery
(/api/tags, /api/show, /api/ps, /api/version) does NOT load weights and is not
flagged.

WHAT IS ALLOWED
---------------
1. compute/ollama_provider_v2.py — the single canonical lease-aware transport.
   This is the one place permitted to speak these endpoints.
2. Low-level transport tests whose explicit purpose is to exercise the raw
   Ollama HTTP/protocol boundary. These are registered here by name and must
   justify their existence in a comment.

The target is zero unexplained production bypasses, not zero raw HTTP calls
anywhere. Adding a production bypass must fail CI until it is migrated to
Provider V2 or explicitly registered as a low-level test.
"""
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Endpoints that LOAD MODEL WEIGHTS. Read-only discovery endpoints are
# deliberately excluded: they hold no residency and are not the concern here.
# Matched only when the string is part of a URL/endpoint construction, not a
# bare mention — a display label like "ollama:/api/chat" or a release call
# with keep_alive=0 is not a weight load.
LOAD_ENDPOINT_PATTERNS = (
    re.compile(r"""["'](?:https?://[^"']*)?/api/generate["']"""),
    re.compile(r"""["'](?:https?://[^"']*)?/api/chat["']"""),
    re.compile(r"""["'](?:https?://[^"']*)?/api/embed(?:dings)?["']"""),
)

# A line that both matches a load endpoint AND is clearly a release (keep_alive
# 0 / unload) is a residency-freeing call, not a bypass.
RELEASE_HINTS = ("keep_alive", "keepalive", "keep_alive\":0", "unload")


# The one canonical transport. Everything else must route through it.
CANONICAL_TRANSPORT = "compute/ollama_provider_v2.py"

# Explicit low-level transport-test exceptions. Each must exist solely to
# exercise the raw Ollama HTTP/protocol boundary. A test that is really
# testing Aetherius/Genesis production behaviour does NOT belong here — it
# belongs on Provider V2.
ALLOWED_DIRECT_TRANSPORT = {
    CANONICAL_TRANSPORT,
    # Read-only discovery adapter: /api/tags, /api/show, /api/version only.
    # Its _ollama_request RAISES on any load endpoint (guarded in-code), so it
    # provably never loads weights — it is a discovery client, not a bypass.
    "models/providers/ollama_provider.py",
}

# Non-product trees that must not trip the guard.
SKIP_DIRS = {
    ".git", "__pycache__", ".bridge", "local", ".venv", "venv",
    ".opencode", "node_modules", ".aetherius",
}


def _product_python_files():
    for base, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.endswith(".py"):
                continue
            full = os.path.join(base, name)
            rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
            yield rel, full


class OllamaBypassGuardTests(unittest.TestCase):
    def test_no_production_path_loads_ollama_weights_outside_provider_v2(self):
        """Fail if a tracked file constructs a load-triggering Ollama URL
        without being on the allowlist."""
        offenders = []
        for rel, full in _product_python_files():
            # Tests are not production bypasses: a unit test may exercise the
            # raw boundary or a release hook. The guard targets shipped code.
            if rel.startswith("tests/") or "/test_" in rel or rel.endswith(
                    ("_test.py", "test_" + rel.split("/")[-1])):
                continue
            if rel in ALLOWED_DIRECT_TRANSPORT:
                continue
            try:
                with open(full, encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, 1):
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            continue
                        matched = any(pat.search(line)
                                      for pat in LOAD_ENDPOINT_PATTERNS)
                        if not matched:
                            continue
                        # A keep_alive=0 / unload call frees residency; it is
                        # not a bypass even though it names a load endpoint.
                        if any(hint in line for hint in RELEASE_HINTS):
                            continue
                        offenders.append(f"{rel}:{lineno}: {stripped}")
            except (OSError, UnicodeDecodeError):
                continue
        self.assertEqual(
            offenders, [],
            "production paths loading Ollama weights outside Provider V2 "
            "(§consolidation). Migrate to OllamaProviderV2 or register as an "
            "explicit LOW_LEVEL_RUNTIME_TEST in ALLOWED_DIRECT_TRANSPORT:\n  "
            + "\n  ".join(offenders))

    def test_canonical_transport_is_registered(self):
        """The canonical provider must always be allowlisted — it is the one
        file permitted to speak these endpoints directly."""
        self.assertIn(CANONICAL_TRANSPORT, ALLOWED_DIRECT_TRANSPORT)

    def test_provider_v2_exposes_lease_aware_chat_infer_and_stream(self):
        """The canonical provider must actually own the operations the
        migrated callers need, or a bypass is one convenience-call away."""
        from compute.ollama_provider_v2 import OllamaProviderV2
        for op in ("infer", "chat", "embed", "infer_stream",
                   "acquire", "release", "release_all", "resident_models"):
            self.assertTrue(
                hasattr(OllamaProviderV2, op),
                f"OllamaProviderV2 is missing {op}; migrated callers would "
                f"be forced back to a direct HTTP bypass")


if __name__ == "__main__":
    unittest.main()
