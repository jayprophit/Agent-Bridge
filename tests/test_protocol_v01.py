"""MIGRATED from v0.2 tests/test_protocol_v01.py — must keep passing in v0.3."""
import unittest

from protocol import normalize_action, parse_model_output, validate_action


class TestCanonical(unittest.TestCase):
    def test_write_canonical(self):
        a, raw, err = parse_model_output('{"action":"write","path":"hello.py","content":"print(1)"}')
        self.assertEqual(err, "")
        self.assertEqual(a, {"action": "write", "path": "hello.py", "content": "print(1)"})

    def test_all_actions(self):
        for text, exp in [
            ('{"action":"list","path":"."}', {"action": "list", "path": "."}),
            ('{"action":"read","path":"a.txt"}', {"action": "read", "path": "a.txt"}),
            ('{"action":"shell","command":"python x.py"}', {"action": "shell", "command": "python x.py"}),
            ('{"action":"finish","message":"done"}', {"action": "finish", "message": "done"}),
        ]:
            a, _, err = parse_model_output(text)
            self.assertEqual(err, "", text)
            self.assertEqual(a, exp, text)

    def test_edit(self):
        a, _, err = parse_model_output('{"action":"edit","path":"f","old":"x","new":"y"}')
        self.assertEqual(err, "")
        self.assertEqual(a["action"], "edit")


class TestVariants(unittest.TestCase):
    def test_name_arguments(self):
        raw = '{"name":"write","arguments":{"filePath":"test.py","content":"print(1)"}}'
        a, _, err = parse_model_output(raw)
        self.assertEqual(err, "", err)
        self.assertEqual(a, {"action": "write", "path": "test.py", "content": "print(1)"})

    def test_markdown_fence(self):
        raw = 'Here you go:\n```json\n{"action":"read","path":"a.txt"}\n```\n'
        a, _, err = parse_model_output(raw)
        self.assertEqual(err, "")
        self.assertEqual(a, {"action": "read", "path": "a.txt"})

    def test_alias_keys(self):
        obj = normalize_action({"action": "edit", "filePath": "f", "oldString": "x", "newString": "y"})
        self.assertEqual(obj.get("path"), "f")
        self.assertEqual(obj.get("old"), "x")
        self.assertEqual(obj.get("new"), "y")


class TestModelHabits(unittest.TestCase):
    """A model that writes text does not always produce valid JSON.

    The output below is the one a real local model produced when asked
    to write a haiku: the JSON was correct, but the string value held a
    real newline instead of the two characters a backslash and an n.
    json.loads refuses that with "Invalid control character", so the
    action was rejected as though the model had said nothing at all,
    and the task failed with "no valid structured action found".

    The refusal was right in the sense that the action could not be
    read, but the output was plainly a structured action, and the model
    had said exactly what it meant.
    """

    RAW = ('```json\n{\n  "action": "write",\n  "path": "haiku.txt",\n'
           '  "content": "Water flows,  \nBeneath the moon,  \n'
           'Silence whispers."\n}\n```')

    def test_a_real_newline_in_a_string_value_is_read(self):
        action, _, err = parse_model_output(self.RAW)
        self.assertEqual(err, "")
        self.assertIsNotNone(action)
        self.assertEqual(action["action"], "write")
        self.assertEqual(action["path"], "haiku.txt")
        self.assertIn("Water flows", action["content"])

    def test_the_newline_is_preserved_in_the_content(self):
        action, _, _ = parse_model_output(self.RAW)
        self.assertIn("\n", action["content"])

    def test_escaped_newlines_still_work(self):
        """The ordinary form must not be disturbed by the relaxed one."""
        action, _, err = parse_model_output(
            '{"action":"write","path":"a.txt","content":"one\\ntwo"}')
        self.assertEqual(err, "")
        self.assertEqual(action["content"], "one\ntwo")

    def test_a_broken_object_is_still_refused(self):
        """The relaxation permits control characters, not broken JSON."""
        action, _, err = parse_model_output('{"action":"write", "path":')
        self.assertIsNone(action)
        self.assertTrue(err)

    def test_an_unknown_action_is_still_refused(self):
        """The relaxation does not let an invalid action through."""
        action, _, err = parse_model_output(
            '{"action":"delete_everything","path":"x","content":"y\\nz"}')
        self.assertIsNone(action)
        self.assertIn("unknown action", err)

    def test_a_write_without_content_is_still_refused(self):
        """Validation still has the last word."""
        action, _, err = parse_model_output(
            '{"action":"write","path":"x","content":"ok\\nhere"}')
        self.assertIsNotNone(action)
        action, _, err = parse_model_output('{"action":"write","path":"x"}')
        self.assertIsNone(action)
        self.assertIn("content", err)


class TestValidationFailures(unittest.TestCase):
    def test_unknown_action(self):
        a, raw, err = parse_model_output('{"action":"delete_v01_unknown_xyz","path":"x"}')
        self.assertIsNone(a)
        self.assertIn("unknown action", err)
    def test_missing_field(self):
        a, _, err = parse_model_output('{"action":"read"}')
        self.assertIsNone(a)
        self.assertIn("path", err)

    def test_garbage(self):
        a, raw, err = parse_model_output("hello world, no json here")
        self.assertIsNone(a)
        self.assertTrue(err)
        self.assertEqual(raw, "hello world, no json here")

    def test_empty(self):
        a, _, err = parse_model_output("   ")
        self.assertIsNone(a)
        self.assertIn("empty", err)

    def test_validate_direct(self):
        ok, res = validate_action({"action": "write", "path": "x"})
        self.assertFalse(ok)
        self.assertIn("content", res)


if __name__ == "__main__":
    unittest.main()
