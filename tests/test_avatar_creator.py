"""Avatar character creator tests (v0.8, convergence).

Standard customization architecture: creation modes, appearance
categories, presentation/voice/personality independence, simple vs
advanced modes, non-destructive history. Geometry morphs stay
PROVIDER_REQUIRED (never faked as rendered).
"""
import unittest

from avatar.creator import (
    CREATION_MODES, CUSTOMIZE_FROM_PRESET, GUIDED_CAMERA_CAPTURE,
    IMAGE_REFERENCE, IMPORT_GLB, IMPORT_GLTF, IMPORT_VRM, PRESET,
    PROFILE_SUPPORTED, PROVIDER_REQUIRED, RANDOM_GENERATE,
    RENDERED_SUPPORTED, SIMPLE_FIELDS, AppearanceProfile, AvatarCreator,
    PersonaProfile, PresetStore, VoiceSelection, list_presets,
    suggest_voices, support_for,
)
from avatar.protocol import CUSTOM, FEMALE, MALE, NEUTRAL


class ModesTests(unittest.TestCase):
    def test_all_modes_listed(self):
        for mode in (PRESET, CUSTOMIZE_FROM_PRESET, RANDOM_GENERATE,
                     IMAGE_REFERENCE, GUIDED_CAMERA_CAPTURE, IMPORT_GLTF,
                     IMPORT_GLB, IMPORT_VRM):
            self.assertIn(mode, CREATION_MODES)

    def test_preset_and_customize(self):
        c = AvatarCreator()
        p = c.create(PRESET, preset="fem-default")
        self.assertEqual(p.presentation, FEMALE)
        q = c.create(CUSTOMIZE_FROM_PRESET, preset="masc-default",
                     hair_colour="red")
        self.assertEqual(q.presentation, MALE)
        self.assertEqual(q.hair_colour, "red")

    def test_random_seeded_deterministic(self):
        c = AvatarCreator()
        a = c.create(RANDOM_GENERATE, seed=7)
        b = c.create(RANDOM_GENERATE, seed=7)
        self.assertEqual(a.to_dict(), b.to_dict())
        d = c.create(RANDOM_GENERATE, seed=8)
        self.assertNotEqual(a.to_dict(), d.to_dict())

    def test_import_contracts(self):
        c = AvatarCreator()
        g = c.create(IMPORT_GLB, asset_path="avatar.glb")
        self.assertEqual(g.avatar_asset, "avatar.glb")
        self.assertEqual(c.create(IMPORT_GLTF, asset_path="a.gltf").source_mode,
                         IMPORT_GLTF)
        self.assertEqual(c.create(IMPORT_VRM, asset_path="a.vrm").source_mode,
                         IMPORT_VRM)
        with self.assertRaises(ValueError):
            c.create(IMPORT_GLB, asset_path="avatar.gltf")

    def test_image_and_capture_need_reference(self):
        c = AvatarCreator()
        with self.assertRaises(ValueError):
            c.create(IMAGE_REFERENCE)
        with self.assertRaises(ValueError):
            c.create(GUIDED_CAMERA_CAPTURE)
        p = c.create(IMAGE_REFERENCE, reference="photo:img1")
        self.assertEqual(p.source_ref, "photo:img1")

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            AvatarCreator().create("SCULPT_FROM_THOUGHT")


class AppearanceTests(unittest.TestCase):
    def test_all_categories_present(self):
        p = AppearanceProfile()
        d = p.to_dict()
        for field_name in ("body_proportions", "body_build", "head_shape",
                           "face_proportions", "jaw", "cheekbones", "chin",
                           "nose", "eyes", "eyebrows", "ears", "mouth_lips",
                           "skin_tone", "hair_style", "hair_colour",
                           "facial_hair", "age_appearance", "scars",
                           "freckles", "tattoos", "piercings", "accessories",
                           "clothing", "footwear", "skins_outfits",
                           "height_cm"):
            self.assertIn(field_name, d)

    def test_presentations(self):
        for profile in (MALE, FEMALE, NEUTRAL, CUSTOM):
            ok, _ = AppearanceProfile(presentation=profile).validate()
            self.assertTrue(ok)
        ok, _ = AppearanceProfile(presentation="FROM_VOICE").validate()
        self.assertFalse(ok)

    def test_support_levels_honest(self):
        # Rendered by the procedural reference GLB.
        self.assertEqual(support_for("eyes"), RENDERED_SUPPORTED)
        # True geometry morphs need a provider (never faked).
        self.assertEqual(support_for("head_shape"), PROVIDER_REQUIRED)
        self.assertEqual(support_for("nose_geometry"), PROVIDER_REQUIRED)
        # Stored profile values.
        self.assertEqual(support_for("skin_tone"), PROFILE_SUPPORTED)
        self.assertEqual(support_for("tattoos"), PROFILE_SUPPORTED)


class IndependenceTests(unittest.TestCase):
    def test_voice_suggested_not_locked(self):
        sugg = suggest_voices(MALE)
        self.assertTrue(sugg)
        # Any voice may be assigned to any presentation.
        p = AppearanceProfile(presentation=MALE)
        v = VoiceSelection(voice_id="fem-voice-a", language="en")
        self.assertEqual(p.presentation, MALE)
        self.assertEqual(v.voice_id, "fem-voice-a")

    def test_personality_separate_from_appearance(self):
        p = AppearanceProfile()
        self.assertNotIn("personality", p.to_dict())
        persona = PersonaProfile(personality="witty", expression_style="bold")
        self.assertEqual(persona.personality, "witty")
        v = VoiceSelection(voice_id="neutral-voice-a")
        self.assertNotIn("pitch", p.to_dict())
        self.assertIn("pitch", v.to_dict())


class Modes_UXTests(unittest.TestCase):
    def test_simple_vs_advanced(self):
        p = AppearanceProfile()
        simple = p.simple_view()
        advanced = p.advanced_view()
        self.assertEqual(set(simple), set(SIMPLE_FIELDS))
        self.assertGreater(len(advanced), len(simple))
        self.assertIn("presentation", simple)
        # Voice is a separate dimension (never collapsed into appearance).
        self.assertNotIn("voice_id", advanced)
        v = VoiceSelection(voice_id="neutral-voice-a")
        self.assertEqual(v.voice_id, "neutral-voice-a")


class HistoryTests(unittest.TestCase):
    def test_apply_undo_redo(self):
        c = AvatarCreator()
        p = c.create(PRESET)
        c.apply_change(p, hair_colour="blue")
        self.assertEqual(p.hair_colour, "blue")
        p = c.undo(p)
        self.assertEqual(p.hair_colour, "brown")
        p = c.redo(p)
        self.assertEqual(p.hair_colour, "blue")
        with self.assertRaises(ValueError):
            c.apply_change(p, nosuchfield="x")

    def test_reset_section_and_all(self):
        c = AvatarCreator()
        p = c.create(PRESET, preset="fem-default")
        c.apply_change(p, hair_colour="green", clothing="formal")
        p = c.reset_section(p, "hair")
        self.assertEqual(p.hair_colour, "brown")
        self.assertEqual(p.clothing, "formal")
        with self.assertRaises(ValueError):
            c.reset_section(p, "aura")
        p = c.reset_all(p)
        self.assertEqual(p.clothing, "casual")

    def test_save_duplicate_versions(self):
        store = PresetStore()
        c = AvatarCreator()
        p = c.create(PRESET)
        v1 = store.save("mine", p)
        self.assertEqual(v1["version"], 1)
        c.apply_change(p, clothing="formal")
        v2 = store.save("mine", p)
        self.assertEqual(v2["version"], 2)
        self.assertEqual(len(store.versions("mine")), 2)
        dup = store.duplicate("mine", "mine-copy")
        self.assertEqual(dup["name"], "mine-copy")
        self.assertIn("mine-copy", store.list())
        with self.assertRaises(ValueError):
            store.duplicate("mine", "mine-copy")

    def test_presets_listed(self):
        self.assertIn("neutral-default", list_presets())


if __name__ == "__main__":
    unittest.main()
