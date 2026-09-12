"""v0.5: reference-shell E2E against mock runtime (no Ollama)."""
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from reference_agent_shell.mock_runtime import factory_for
from reference_agent_shell.shell import EmbeddedClient, Shell
from reference_agent_shell.prefs import Prefs
from runtime import AgentRuntime, RuntimeConfig


def _shell(tmp: Path, scripts: dict, buf: io.StringIO, **rkw) -> Shell:
    ws = tmp / "w"
    ws.mkdir(exist_ok=True)
    args = dict(allowed_workspace_roots=[str(tmp)])
    args.update(rkw)
    rt = AgentRuntime(RuntimeConfig(**args),
                      provider_factory=factory_for(scripts))
    return Shell(EmbeddedClient(rt), Prefs(tmp / "prefs.json"), runtime=rt,
                 out=buf), ws


class TestShellMockE2E(unittest.TestCase):
    def test_build_flow(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_shell_"))
        try:
            buf = io.StringIO()
            shell, ws = _shell(tmp, {"*": [
                '{"action":"write","path":"ok.txt","content":"mock hi"}',
                '{"action":"finish","message":"mock success"}']}, buf)
            with redirect_stdout(buf):
                shell.dispatch(f"new {ws} build")
                shell.dispatch("task mock build task")
                shell.dispatch("status")
                shell.dispatch("result")
                shell.dispatch("manifest")
                shell.dispatch("scorecard")
            out = buf.getvalue()
            self.assertIn("COMPLETED", out)
            self.assertIn("ok.txt", out)
            self.assertTrue((ws / "ok.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_plan_flow_zero_mutation(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_shellp_"))
        try:
            buf = io.StringIO()
            shell, ws = _shell(tmp, {"*": [
                '{"action":"write","path":"evil.txt","content":"x"}',
                '{"action":"finish","message":"1. create evil.txt"}']}, buf)
            with redirect_stdout(buf):
                shell.dispatch(f"new {ws} plan")
                shell.dispatch("task mock plan task")
            out = buf.getvalue()
            self.assertIn("COMPLETED", out)
            # plan mode performs ZERO task mutation (.bridge bookkeeping only)
            self.assertFalse((ws / "evil.txt").exists())
            self.assertEqual([p.name for p in ws.iterdir()
                              if not p.name.startswith(".bridge")], [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_approval_flow(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_shella_"))
        try:
            buf = io.StringIO()
            shell, ws = _shell(
                tmp, {"*": ['{"action":"write","path":"g.txt","content":"x"}',
                            '{"action":"finish","message":"ok"}']}, buf)
            with redirect_stdout(buf):
                shell.dispatch(f"new {ws} build")
                # flip session to interactive approvals is covered at unit
                # level; here verify the approval UI renders a request card
                from reference_agent_shell import views
                card = views.approval_card(
                    "ap-1", {"action": "write", "path": "g.txt"},
                    {"risk": "RISKY", "reason": "needs human",
                     "diff_preview": "would modify g.txt"})
                shell.emit(card)
            self.assertIn("approval ap-1", buf.getvalue())
            self.assertIn("RISKY", buf.getvalue())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cancel_and_rollback_flow(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_shellc_"))
        try:
            buf = io.StringIO()
            shell, ws = _shell(tmp, {"*": [
                '{"action":"write","path":"c.txt","content":"v1"}',
                '{"action":"finish","message":"ok"}']}, buf)
            with redirect_stdout(buf):
                shell.dispatch(f"new {ws} build")
                shell.dispatch("task mock task")
                shell.dispatch("rollback CONFIRM")
                shell.dispatch("timeline")
            out = buf.getvalue()
            self.assertIn("rollback ok=True", out)
            self.assertFalse((ws / "c.txt").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_export_and_history(self):
        tmp = Path(tempfile.mkdtemp(prefix="v05_shelle_"))
        try:
            buf = io.StringIO()
            shell, ws = _shell(tmp, {"*": [
                '{"action":"finish","message":"nothing to do"}']}, buf)
            with redirect_stdout(buf):
                shell.dispatch(f"new {ws} build")
                shell.dispatch("task trivial")
                shell.dispatch("export json")
                shell.dispatch("history")
            out = buf.getvalue()
            self.assertIn("exported", out)
            self.assertIn("COMPLETED", out)
        finally:
            for f in ("shell_export.json", "shell_export.markdown",
                      "shell_export.jsonl"):
                try:
                    Path(f).unlink()
                except OSError:
                    pass
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
