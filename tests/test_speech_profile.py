"""Speech backend profile tests (P21, REQ-p21-speech-profile)."""
import unittest

from multimodal import probes
from multimodal.router import ModalityRoute, MultimodalRouter, ModalityBackend
from multimodal.speech_profile import (
    SpeechBackendProfile,
    SpeechLicence,
    SpeechPrivacy,
    SpeechProfileError,
    SpeechProfileRegistry,
    attach_profiles,
    detect_sapi_profile,
    validate_profile,
)


def profile(**over):
    base = {
        "backend_profile_id": "whisper-local-stt",
        "backend_id": "whisper-cpp",
        "version": "1.0.0",
        "status": "NOT_INSTALLED",
        "capabilities": ["STT"],
        "languages": ["en"],
        "streaming_in": False,
        "streaming_out": False,
        "offline_capable": True,
        "installed": False,
        "privacy": SpeechPrivacy(processes_locally=True, network_required=False),
        "licence": SpeechLicence(identifier="MIT"),
        "consent_required": [],
        "provenance": "BACKEND_METADATA",
        "evidence_ref": "fixture",
    }
    base.update(over)
    return SpeechBackendProfile(**base)


class TestValidation(unittest.TestCase):
    def test_valid_and_sparse_profiles(self):
        self.assertEqual(validate_profile(profile()), [])
        sparse = SpeechBackendProfile(backend_profile_id="s", backend_id="b")
        self.assertEqual(validate_profile(sparse), [])
        self.assertFalse(sparse.installed)
        self.assertEqual(sparse.status, "UNKNOWN")

    def test_malformed_rejected(self):
        self.assertIn("backend_profile_id is required", validate_profile(profile(backend_profile_id="  ")))
        self.assertIn("backend_id is required", validate_profile(profile(backend_id="")))
        self.assertIn("version is required", validate_profile(profile(version="")))
        bad_status = validate_profile(profile(status="MAGIC"))
        self.assertTrue(any("status must be" in p for p in bad_status))
        bad_cap = validate_profile(profile(capabilities=["TELEPATHY"]))
        self.assertTrue(any("unknown speech capability" in p for p in bad_cap))
        bad_lang = validate_profile(profile(languages=["en", " "]))
        self.assertTrue(any("languages must be" in p for p in bad_lang))
        bad_prov = validate_profile(profile(provenance="vibes"))
        self.assertTrue(any("provenance must be" in p for p in bad_prov))
        bad_priv = validate_profile(profile(privacy=SpeechPrivacy(processes_locally="maybe")))
        self.assertTrue(any("privacy.processes_locally" in p for p in bad_priv))
        bad_lic = validate_profile(profile(licence=SpeechLicence(commercial_use="yes")))
        self.assertTrue(any("licence.commercial_use" in p for p in bad_lic))
        bad_consent = validate_profile(profile(consent_required=["voice-cloning", ""]))
        self.assertTrue(any("consent_required" in p for p in bad_consent))

    def test_installed_requires_matching_status(self):
        bad = validate_profile(profile(installed=True, status="NOT_INSTALLED"))
        self.assertTrue(any("INSTALLED or AVAILABLE" in p for p in bad))
        good = validate_profile(profile(installed=True, status="INSTALLED"))
        self.assertEqual(good, [])


class TestRegistry(unittest.TestCase):
    def test_register_lookup_list_deterministic(self):
        reg = SpeechProfileRegistry()
        reg.register(profile(backend_profile_id="b"))
        reg.register(profile(backend_profile_id="a"))
        self.assertEqual([p.backend_profile_id for p in reg.list()], ["a", "b"])
        self.assertEqual(reg.lookup("a").backend_id, "whisper-cpp")
        self.assertIsNone(reg.lookup("ghost"))

    def test_idempotent_identical_conflicting_overwrite(self):
        reg = SpeechProfileRegistry()
        reg.register(profile())
        reg.register(profile())
        with self.assertRaises(SpeechProfileError):
            reg.register(profile(version="2.0.0"))
        with self.assertRaises(SpeechProfileError):
            reg.register(profile(backend_profile_id=""))


class TestHonesty(unittest.TestCase):
    def test_not_installed_stays_not_installed(self):
        p = profile()
        self.assertEqual(p.status, "NOT_INSTALLED")
        self.assertFalse(p.installed)
        # NOT_INSTALLED is not UNSUPPORTED: capability declared, backend absent.
        self.assertEqual(p.capabilities, ["STT"])
        self.assertTrue(p.offline_capable)

    def test_unknown_is_not_false(self):
        sparse = SpeechBackendProfile(backend_profile_id="s", backend_id="b")
        self.assertEqual(sparse.status, "UNKNOWN")
        self.assertEqual(sparse.languages, [])
        self.assertIsNone(sparse.privacy.processes_locally)

    def test_consent_required_is_not_consent_present(self):
        p = profile(consent_required=["voice-cloning"])
        self.assertIn("voice-cloning", p.consent_required)
        self.assertNotIn("consent_present", p.__dict__)
        self.assertNotIn("consent_obtained", p.__dict__)

    def test_no_credential_fields(self):
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(SpeechBackendProfile)}
        for banned in ("api_key", "apikey", "access_token", "token", "password",
                       "secret", "private_key", "credential", "credentials"):
            self.assertNotIn(banned, field_names)
        # Consent names requirements; possession is never represented.
        self.assertNotIn("consent_present", field_names)
        self.assertNotIn("consent_obtained", field_names)


class TestRouterIntegration(unittest.TestCase):
    def test_attach_enriches_without_changing_routing(self):
        router = MultimodalRouter([ModalityBackend(backend_id="whisper-cpp", modality="STT", kind="none")])
        route = router.route("STT")
        self.assertEqual(route.status, "NOT_INSTALLED")
        enriched = attach_profiles(route, [profile()])
        self.assertEqual(enriched["status"], "NOT_INSTALLED")
        self.assertEqual(enriched["backend_id"], "whisper-cpp")
        self.assertEqual(len(enriched["profiles"]), 1)
        self.assertEqual(enriched["profiles"][0]["backend_profile_id"], "whisper-local-stt")
        empty = attach_profiles(ModalityRoute(modality="TTS"), [])
        self.assertEqual(empty["profiles"], [])
        self.assertEqual(empty["status"], "PROVIDER_REQUIRED")

    def test_detect_sapi_reports_honestly(self):
        real = probes.probe_sapi_voices
        try:
            probes.probe_sapi_voices = lambda: {"present": True, "backend": "sapi", "voices": ["Microsoft David"]}
            installed = detect_sapi_profile()
            self.assertEqual(installed.status, "INSTALLED")
            self.assertTrue(installed.installed)
            self.assertTrue(installed.offline_capable)
            self.assertEqual(validate_profile(installed), [])
            probes.probe_sapi_voices = lambda: {"present": False, "backend": "none", "status": "NOT_INSTALLED"}
            absent = detect_sapi_profile()
            self.assertEqual(absent.status, "NOT_INSTALLED")
            self.assertFalse(absent.installed)
        finally:
            probes.probe_sapi_voices = real


if __name__ == "__main__":
    unittest.main()
