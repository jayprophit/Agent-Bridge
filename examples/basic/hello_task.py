"""Basic example (offline): run one bridge task with a scripted provider."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bridge import run_bridge
from config import BridgeConfig
from tests.helpers import FakeProvider

ws = Path(tempfile.mkdtemp(prefix="ab_example_"))
cfg = BridgeConfig(workspace=ws, mode="build", approval="AUTO_SAFE",
                   max_steps=6, non_interactive=True, enable_reviewer=False)
out = run_bridge(cfg, "write hello.txt with: hi", provider=FakeProvider([
    '{"action":"write","path":"hello.txt","content":"hi"}',
    '{"action":"finish","message":"done"}']))
print("finished:", out.get("finished"), "| file:",
      (ws / "hello.txt").read_text(encoding="utf-8"))
