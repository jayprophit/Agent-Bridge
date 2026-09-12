"""OCR / STT / image-provider tests (v0.8, real local backends where present)."""
import os
import tempfile
import unittest

from multimodal import ocr as ocr_backend
from multimodal import stt as stt_backend
from multimodal import image_providers


class WindowsOcrTests(unittest.TestCase):
    def test_engine_available(self):
        res = ocr_backend.is_available()
        self.assertTrue(res.get("present"), res)
        self.assertEqual(res.get("backend"), "windows-ocr")

    def test_fixture_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix="ab_ocr_test_") as d:
            img = os.path.join(d, "fixture.png")
            rendered = ocr_backend.render_fixture_text("BRIDGE OCR 4567", img)
            self.assertTrue(rendered.get("ok"), rendered)
            res = ocr_backend.recognize(img)
            self.assertTrue(res.get("ok"), res)
            self.assertIn("BRIDGE OCR 4567", res.get("text", ""))
            self.assertTrue(res.get("words"), "expected word boxes")
            for word in res["words"]:
                self.assertIn("box", word)
                self.assertEqual(len(word["box"]), 4)
            self.assertEqual(res.get("provenance", "")[:11], "windows-ocr")
            # Confidence is honestly absent from WinRT.
            self.assertIn("confidence", res)

    def test_missing_file_is_not_verified(self):
        res = ocr_backend.recognize(os.path.join("nonexistent", "x.png"))
        self.assertFalse(res.get("ok"))


class SttInterfaceTests(unittest.TestCase):
    def test_canonical_interface_complete(self):
        backend = stt_backend.STTBackend()
        self.assertIn("list_backends", dir(backend))
        self.assertIn("status", dir(backend))
        self.assertIn("languages", dir(backend))
        self.assertIn("transcribe_file", dir(backend))
        self.assertIn("start_stream", dir(backend))
        self.assertIn("stop_stream", dir(backend))

    def test_no_backend_reports_not_installed(self):
        res = stt_backend.probe_local()
        self.assertFalse(res["present"])
        self.assertEqual(
            stt_backend.STTBackend().transcribe_file("x.wav").status, "NOT_INSTALLED")

    def test_whisper_adapter_unconfigured(self):
        adapter = stt_backend.WhisperCompatibleAdapter()
        self.assertEqual(adapter.status()["status"], "NOT_INSTALLED")
        res = adapter.transcribe_file("x.wav")
        self.assertFalse(res.ok)
        # Unknown record shape never crashes the contract.
        bad = stt_backend.WhisperCompatibleAdapter(endpoint="http://127.0.0.1:9/")
        self.assertEqual(bad.status()["status"], "NOT_INSTALLED")

    def test_stt_records_present(self):
        from tools.tool_audit import collect_records
        ids = {r.tool_id for r in collect_records()}
        for tid in ("stt.list_backends", "stt.status", "stt.transcribe_file",
                    "stt.start_stream", "stt.stop_stream", "stt.languages"):
            self.assertIn(tid, ids)

    def test_directory_tools_execute_without_backend(self):
        from tools.cat_media import SttDirectoryAdapter
        out = SttDirectoryAdapter({}, "stt.list_backends").execute({})
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("backends"), [])
        status = SttDirectoryAdapter({}, "stt.status").execute({})
        self.assertEqual(status.get("status"), "NOT_INSTALLED")


class ImageProviderTests(unittest.TestCase):
    def test_discovery_shape(self):
        found = image_providers.discover()
        self.assertTrue(any(e.endpoint_id == "comfyui" for e in found))
        self.assertTrue(any(e.endpoint_id == "a1111" for e in found))
        for e in found:
            self.assertIn("reachable", e.to_dict())

    def test_contracts_serialize(self):
        gen = image_providers.GenerationRequest(prompt="a red square", width=512,
                                                height=512, seed=7)
        self.assertEqual(gen.to_dict()["seed"], 7)
        edit = image_providers.EditRequest(source_artifact="artifact:x",
                                           instruction="make it blue")
        self.assertEqual(edit.to_dict()["source_artifact"], "artifact:x")

    def test_no_local_endpoint_means_provider_required(self):
        from multimodal import MultimodalRouter, local_backends_from_registries
        from tools.registry import ToolRegistry
        from tools.tool_audit import collect_records
        reg = ToolRegistry()
        for rec in collect_records():
            try:
                reg.register(rec)
            except ValueError:
                pass
        route = MultimodalRouter(local_backends_from_registries(reg, None)).route(
            "IMAGE_GENERATION")
        # Deterministic stdlib ops exist but are not generative; without a
        # local endpoint the generative path must not claim AVAILABLE.
        if route.backend_id == "bridge-image-deterministic":
            self.assertIn("not generative", route.reasons[0])
        else:
            self.assertEqual(route.status, "PROVIDER_REQUIRED")


if __name__ == "__main__":
    unittest.main()
