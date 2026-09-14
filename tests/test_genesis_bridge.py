"""Genesis bridge contract tests (no runtime)."""
import unittest

from genesis_bridge import AvatarBinding, GenesisIdentity, GenesisSession


class TestGenesisContracts(unittest.TestCase):
    def test_identity_survives_rotation(self):
        g = GenesisIdentity(genesis_id="g-1", active_model="a:1b")
        out = g.rotate_model("b:3b")
        self.assertTrue(out["identity_preserved"])
        self.assertEqual(g.genesis_id, "g-1")
        self.assertEqual(g.active_model, "b:3b")
        self.assertIn("a:1b", g.model_history)
        d = g.to_dict()
        self.assertEqual(d["genesis_id"], "g-1")

    def test_session_shape(self):
        s = GenesisSession(session_id="gs-1", genesis_id="g-1",
                           bridge_session_id="s-1", objective="demo")
        self.assertEqual(s.state, "OPEN")
        self.assertEqual(s.bridge_session_id, "s-1")

    def test_avatar_projection(self):
        a = AvatarBinding(genesis_id="g-1")
        out = a.project({"state": "working", "summary": "building"})
        self.assertEqual(out["state"], "working")
        self.assertEqual(out["genesis_id"], "g-1")


if __name__ == "__main__":
    unittest.main()
