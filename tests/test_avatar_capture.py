"""Guided camera capture + photo-to-avatar tests (v0.8, convergence).

Ephemeral raw capture, explicit permission, derive-then-delete default,
photo reference contract, reconstruction provider-required. Fixture
frames only (no camera hardware, no biometric retention).
"""
import os
import tempfile
import unittest

from avatar.capture import (
    DELETE_AFTER_DERIVATION, DERIVED_APPEARANCE_PROFILE,
    DERIVED_LANDMARKS, EPHEMERAL_RAW_CAPTURE, GENERATED_AVATAR_ASSET,
    REQUIRED_VIEWS, RETAIN_EXPLICIT, GuidedCaptureSession, PhotoTo3DProvider,
    capture_view, derive_from_capture, discard_raw, finalize_capture,
    upload_photo_reference,
)


class GuidedFlowTests(unittest.TestCase):
    def test_starts_ready_front_first(self):
        s = GuidedCaptureSession(session_id="cap-1")
        self.assertEqual(s.status, "READY")
        self.assertEqual(s.next_view(), "front")
        prog = s.progress()
        self.assertEqual(prog["captured"], 0)
        self.assertEqual(prog["required"], len(REQUIRED_VIEWS))

    def test_permission_required(self):
        s = GuidedCaptureSession(session_id="cap-2")
        with tempfile.TemporaryDirectory(prefix="ab_cap_") as d:
            with self.assertRaises(PermissionError):
                capture_view(s, "front", d)

    def test_full_sequence_in_order(self):
        s = GuidedCaptureSession(session_id="cap-3", camera_permission=True)
        with tempfile.TemporaryDirectory(prefix="ab_cap_") as d:
            for view in REQUIRED_VIEWS:
                self.assertEqual(s.next_view(), view)
                frame = capture_view(s, view, d)
                self.assertEqual(frame.kind, EPHEMERAL_RAW_CAPTURE)
                self.assertTrue(os.path.exists(frame.path))
            self.assertIsNone(s.next_view())
            self.assertEqual(s.status, "COMPLETE")
            with self.assertRaises(ValueError):
                capture_view(s, "front", d)
            with self.assertRaises(ValueError):
                capture_view(s, "aura", d)

    def test_derive_requires_complete(self):
        s = GuidedCaptureSession(session_id="cap-4", camera_permission=True)
        with tempfile.TemporaryDirectory(prefix="ab_cap_") as d:
            capture_view(s, "front", d)
            with self.assertRaises(ValueError):
                derive_from_capture(s)


class LifecycleTests(unittest.TestCase):
    def _full_session(self, d):
        s = GuidedCaptureSession(session_id="cap-5", camera_permission=True)
        for view in REQUIRED_VIEWS:
            capture_view(s, view, d)
        return s

    def test_default_deletes_raw(self):
        with tempfile.TemporaryDirectory(prefix="ab_cap_") as d:
            s = self._full_session(d)
            paths = [f.path for f in s.captured.values()]
            self.assertEqual(len(paths), len(REQUIRED_VIEWS))
            out = finalize_capture(s)
            self.assertEqual(out["disposition"]["retention"],
                             DELETE_AFTER_DERIVATION)
            self.assertEqual(out["disposition"]["removed"], len(REQUIRED_VIEWS))
            for p in paths:
                self.assertFalse(os.path.exists(p),
                                 f"raw capture retained: {p}")
            self.assertEqual(s.status, "DISCARDED")
            self.assertEqual(dict(s.captured), {})

    def test_explicit_retain_keeps_with_audit(self):
        with tempfile.TemporaryDirectory(prefix="ab_cap_") as d:
            s = self._full_session(d)
            s.retention = RETAIN_EXPLICIT
            out = finalize_capture(s)
            self.assertEqual(out["disposition"]["removed"], 0)
            kept = out["disposition"]["kept"]
            self.assertEqual(len(kept), len(REQUIRED_VIEWS))
            for p in kept:
                self.assertTrue(os.path.exists(p))
            # Test cleans up explicitly retained fixtures.
            discard_raw(s)

    def test_derived_separated_from_raw(self):
        with tempfile.TemporaryDirectory(prefix="ab_cap_") as d:
            s = self._full_session(d)
            derived = derive_from_capture(s)
            self.assertIn("landmarks", derived)
            self.assertIn("appearance", derived)
            self.assertIn("asset", derived)
            self.assertFalse(derived["asset"]["photorealistic"])
            self.assertEqual(derived["landmarks"]["front"]["origin"],
                             DERIVED_LANDMARKS)
            self.assertEqual(derived["appearance"]["origin"],
                             DERIVED_APPEARANCE_PROFILE)
            self.assertEqual(derived["asset"]["asset"], GENERATED_AVATAR_ASSET)
            discard_raw(s)


class PhotoTests(unittest.TestCase):
    def test_upload_contract(self):
        with tempfile.TemporaryDirectory(prefix="ab_photo_") as d:
            img = os.path.join(d, "face.png")
            with open(img, "wb") as f:
                f.write(b"\x89PNG fixture\n" * 16)
            ref = upload_photo_reference(img)
            self.assertTrue(ref["ok"])
            self.assertTrue(ref["reference"].startswith("photo:"))
            self.assertEqual(ref["kind"], EPHEMERAL_RAW_CAPTURE)
        with self.assertRaises(FileNotFoundError):
            upload_photo_reference(os.path.join("nonexistent", "x.png"))
        with tempfile.TemporaryDirectory(prefix="ab_photo_") as d:
            bad = os.path.join(d, "notes.txt")
            with open(bad, "w") as f:
                f.write("not an image")
            with self.assertRaises(ValueError):
                upload_photo_reference(bad)

    def test_reconstruction_provider_required(self):
        prov = PhotoTo3DProvider()
        st = prov.status()
        self.assertEqual(st["status"], "PROVIDER_REQUIRED")
        res = prov.reconstruct("photo:face.png")
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "PROVIDER_REQUIRED")
        # A configured backend reports AVAILABLE (contract shape).
        real = PhotoTo3DProvider(backend="local-landmarks")
        self.assertEqual(real.status()["status"], "AVAILABLE")
        ok = real.reconstruct("photo:face.png")
        self.assertTrue(ok["ok"])


if __name__ == "__main__":
    unittest.main()
