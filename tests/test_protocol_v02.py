"""MIGRATED from v0.2 tests/test_protocol_v02.py — must keep passing in v0.3."""
import unittest

from protocol import ACTIONS, parse_model_output, validate_action


class TestNewActions(unittest.TestCase):
    def test_action_set(self):
        for a in ("mkdir", "delete", "move", "copy", "patch", "search",
                  "exists", "stat", "test"):
            self.assertIn(a, ACTIONS)

    def test_mkdir_delete(self):
        a, _, err = parse_model_output('{"action":"mkdir","path":"demo"}')
        self.assertEqual(err, "")
        self.assertEqual(a["action"], "mkdir")
        a, _, err = parse_model_output('{"action":"delete","path":"demo/x.txt"}')
        self.assertEqual(err, "")
        self.assertEqual(a["action"], "delete")

    def test_move_copy_aliases(self):
        a, _, err = parse_model_output(
            '{"name":"move","arguments":{"source":"a","destination":"b"}}')
        self.assertEqual(err, "", err)
        self.assertEqual(a, {"action": "move", "src": "a", "dest": "b"})
        a, _, err = parse_model_output('{"action":"copy","from":"a","to":"b"}')
        self.assertEqual(err, "", err)
        self.assertEqual(a["action"], "copy")

    def test_patch_search_exists_stat_test(self):
        for text in [
            '{"action":"patch","path":"f","old":"x","new":"y"}',
            '{"action":"search","pattern":"GENESIS","path":"."}',
            '{"action":"exists","path":"f"}',
            '{"action":"stat","path":"f"}',
            '{"action":"test","command":"python -m pytest"}',
        ]:
            a, _, err = parse_model_output(text)
            self.assertEqual(err, "", text)
            self.assertTrue(a["action"], text)

    def test_patch_needs_all_fields(self):
        ok, err = validate_action({"action": "patch", "path": "f", "old": "x"})
        self.assertFalse(ok)

    def test_fenced_new_action(self):
        a, _, err = parse_model_output('```json\n{"action":"stat","path":"."}\n```')
        self.assertEqual(err, "")
        self.assertEqual(a["action"], "stat")


if __name__ == "__main__":
    unittest.main()
