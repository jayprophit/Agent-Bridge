"""Tool-use example (offline): route a real filesystem write."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from executor import Executor
from tools.cat_core import FsAdapter, fs_records
from tools.registry import ToolRegistry
from tools.router import ToolRouter

ws = Path(tempfile.mkdtemp(prefix="ab_example_"))
ex = Executor(workspace=ws)
reg = ToolRegistry()
for rec in fs_records():
    try:
        reg.register(rec, FsAdapter({"executor": ex}, rec.tool_id))
    except ValueError:
        pass
router = ToolRouter(reg)
res = router.call("filesystem.write",
                  {"path": "note.txt", "content": "via router"},
                  {"profile": "AUTONOMOUS_SANDBOX"})
print("ok:", res.get("ok"), "| file:",
      (ws / "note.txt").read_text(encoding="utf-8"))
