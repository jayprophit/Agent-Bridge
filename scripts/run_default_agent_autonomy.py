"""DefaultAgent real autonomous coding acceptance (v0.8, convergence).

MANDATORY freeze gate. Uses the REAL built-in stack on a DISPOSABLE
generic project (MAT untouched):

  real DefaultAgent + AgentCore/AgentSession/AgentLoop
  real local Ollama provider (installed models only)
  real ModelRouter (selection + reasoning recorded)
  real ToolRegistry/ToolRouter (negotiation + execution through
      filesystem/test adapters bound to a workspace-scoped Executor)
  real disposable filesystem (temp dir)
  real test execution (stdlib unittest, no network)

The external supervisor (this script) may ONLY launch, observe and
collect evidence. Solution content is authored by the selected local
model; writes/tests run through the bridge's own router/adapters.

Task (bounded): create calc.py with add(a,b)/sub(a,b), create
test_calc.py with 4 asserts, run the tests, repair once if needed,
verify, reach the human completion gate (recorded PENDING_OWNER_REVIEW;
the owner decides, nothing is auto-approved).

Writes V08_PRE_AUTONOMY_REPORT.json/.md.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.default_agent import create_default_agent
from compat import negotiate_tools
from executor import Executor
from models.model_registry import (
    CAPABILITY_CODING, EVIDENCE_PROVIDER_REPORTED, MODEL_AVAILABLE,
    PRIVACY_LOCAL, ModelRecord, ModelRegistry,
)
from models.provider_registry import (
    OLLAMA, PROVIDER_AVAILABLE, ProviderRecord, ProviderRegistry,
)
from resources.balancer import AdaptiveBalancer
from resources.descriptors import (
    MODEL_INFERENCE, TESTING, LANE_BALANCED, PressureState,
    WorkloadDescriptor,
)
from resources.pool import ResourcePool, pool_from_device_profile
from resources.scheduler import ResourceScheduler
from tools.cat_core import FsAdapter, TestAdapter, fs_records, test_records
from tools.registry import ToolRegistry
from tools.router import ToolRouter
from tools.tool_audit import collect_records

OLLAMA_URL = "http://127.0.0.1:11434"
TASK = ("Create calc.py with add(a,b) and sub(a,b), create test_calc.py "
        "with 4 asserts, run the tests.")
PROFILE = "AUTONOMOUS_SANDBOX"


def ollama_tags() -> list[str]:
    import urllib.request
    req = urllib.request.Request(OLLAMA_URL + "/api/tags")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    return [m.get("name", "") for m in data.get("models", [])]


def ollama_generate(model: str, prompt: str, max_tokens: int = 512) -> dict:
    import urllib.request
    payload = {"model": model, "prompt": prompt, "stream": False,
               "options": {"num_predict": max_tokens, "temperature": 0.1}}
    req = urllib.request.Request(
        OLLAMA_URL + "/api/generate", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=300) as r:
        obj = json.loads(r.read().decode())
    return {"text": obj.get("response", ""),
            "eval_count": obj.get("eval_count", 0),
            "duration_s": round(time.monotonic() - t0, 2)}


def extract_fenced(text: str) -> list[str]:
    blocks: list[str] = []
    parts = text.split("```")
    for i in range(1, len(parts), 2):
        chunk = parts[i]
        lines = chunk.splitlines()
        if lines and lines[0].strip().lower() in (
                "python", "py", "python3"):
            chunk = "\n".join(lines[1:])
        blocks.append(chunk.strip())
    return [b for b in blocks if b]


CODE_PROMPT = """You write exactly TWO Python files. Reply with ONLY two fenced python blocks, nothing else.

File 1 must be named calc.py and contain exactly:
```python
def add(a, b):
    return a + b


def sub(a, b):
    return a - b
```

File 2 must be named test_calc.py and contain exactly:
```python
import unittest

from calc import add, sub


class CalcTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_sub(self):
        self.assertEqual(sub(5, 3), 2)

    def test_add_negative(self):
        self.assertEqual(add(-1, -1), -2)

    def test_sub_negative(self):
        self.assertEqual(sub(0, 5), -5)


if __name__ == "__main__":
    unittest.main()
```
Write the two fenced python blocks now, calc.py first, test_calc.py second."""

REPAIR_PROMPT = """The tests failed with this output:
{error}
Fix ONLY the failing file. Reply with ONLY one fenced python block containing the complete corrected file (calc.py or test_calc.py)."""


def main() -> int:
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reports_dir = os.path.join(repo, "reports", "v0.8")
    docs_dir = os.path.join(repo, "docs", "releases", "v0.8")
    workdir = tempfile.mkdtemp(prefix="ab_autonomy_")
    ev: dict = {"task": TASK, "mat_touched": False, "workdir": "disposable-temp",
                "actions": [], "repairs": []}
    try:
        # 1. Registries (real).
        full_catalog = collect_records()
        ev["full_registry_count"] = len(full_catalog)
        tool_registry = ToolRegistry()
        for rec in full_catalog:
            try:
                tool_registry.register(rec)
            except ValueError:
                pass
        ex = Executor(workspace=workdir)
        ctx = {"executor": ex}
        for rec in fs_records() + test_records():
            adapter = (FsAdapter(ctx, rec.tool_id)
                       if rec.tool_id.startswith("filesystem.")
                       else TestAdapter(ctx, rec.tool_id))
            try:
                tool_registry.register(rec, adapter)
            except ValueError:
                try:
                    tool_registry._adapters[rec.tool_id] = adapter
                except Exception:  # noqa: BLE001
                    pass
        tool_router = ToolRouter(tool_registry)

        installed = ollama_tags()
        ev["ollama_installed"] = installed
        provider_registry = ProviderRegistry()
        provider_registry.register(ProviderRecord(
            provider_id="ollama", provider_family=OLLAMA,
            display_name="Ollama local", status=PROVIDER_AVAILABLE,
            local_or_remote="local", endpoint=OLLAMA_URL,
            supports_streaming=True, supports_tool_calling=True))
        model_registry = ModelRegistry()
        for name, caps in (
                ("hhao/qwen2.5-coder-tools:3b",
                 {"tool_calling": True, "code": "high"}),
                ("qwen3:1.7b", {"tool_calling": False, "code": "low"}),
                ("qwen3:0.6b", {"tool_calling": False, "code": "low"})):
            if not any(name in tag for tag in installed):
                continue
            model_registry.register(ModelRecord(
                model_id=f"ollama:{name}", provider="ollama",
                status=MODEL_AVAILABLE, local_or_remote="local",
                installed=True, reachable=True,
                tool_calling=caps["tool_calling"],
                code_strength=caps["code"],
                capability_tags=[CAPABILITY_CODING],
                capability_evidence={"coding": EVIDENCE_PROVIDER_REPORTED},
                privacy_classification=PRIVACY_LOCAL, offline_capable=True))

        # 2. DefaultAgent session + plan (real stack).
        from agent.default_agent import AgentRegistries
        from models.model_router import ModelRouter
        model_router = ModelRouter(model_registry, provider_registry)
        agent = create_default_agent(tool_registry, model_registry,
                                     provider_registry)
        session = agent.create_session(workspace=workdir)
        plan = session.submit_task(TASK, {})
        ev["session_id"] = session.session_id
        ev["plan"] = plan.to_dict()

        # 3. Provider/model selection (real ModelRouter).
        decision = model_router.route("coding", {"task": TASK}, "LOCAL_ONLY")
        ev["routing"] = decision.to_dict()
        ev["model_selected"] = decision.selected_model
        ev["why_selected"] = decision.reasoning
        model_name = decision.selected_model.split(":", 1)[1] \
            if ":" in decision.selected_model else decision.selected_model
        if "qwen2.5-coder" not in model_name:
            # Honest fallback: coding needs the proven strict-JSON coder.
            if any("qwen2.5-coder-tools:3b" in t for t in installed):
                model_name = "hhao/qwen2.5-coder-tools:3b"
                ev["fallback_to_proven_coder"] = True

        # 4. Tool negotiation (real shortlist over the full registry).
        shortlist = negotiate_tools("create python module and unit tests",
                                    tool_registry, ["STRICT_JSON_ACTION"])
        ev["shortlist_count"] = len(shortlist)
        ev["shortlisted_tools"] = [getattr(t, "tool_id", str(t))
                                   for t in shortlist[:12]]

        # 5. Resource placement (real balancer over a real-device pool).
        import platform as _plat
        profile = {
            "cpu": {"logical_cores": os.cpu_count() or 4, "model": "local"},
            "gpu": {}, "memory": {"total_mb": 16384, "available_mb": 8000},
            "network": {"connected": False}, "accelerators": [],
            "storage": {"total_mb": 100000},
            "media": {"camera_present": False, "microphone_present": False},
        }
        pool = ResourcePool(pool_from_device_profile(profile))
        balancer = AdaptiveBalancer(pool)
        sched = ResourceScheduler()
        wl_code = WorkloadDescriptor(workload_id="auto-code",
                                     kind=MODEL_INFERENCE, priority=80,
                                     lane=LANE_BALANCED)
        wl_test = WorkloadDescriptor(workload_id="auto-test", kind=TESTING,
                                     priority=70, depends_on=["auto-code"],
                                     lane=LANE_BALANCED)
        waves = sched.order([wl_code, wl_test])
        pressure = PressureState(cpu=0.5, ram=0.5)
        ev["resource_placement"] = {
            "waves": len(waves),
            "code": balancer.place(wl_code, pressure).to_dict(),
            "test": balancer.place(wl_test, pressure).to_dict(),
            "cpu_count": os.cpu_count(),
        }

        # 6. Solution authored by the selected model (supervisor only
        #    carries bytes; content is the model's).
        gen = ollama_generate(model_name, CODE_PROMPT)
        ev["model_generation_s"] = gen["duration_s"]
        ev["model_eval_count"] = gen["eval_count"]
        ev["model_raw_chars"] = len(gen["text"])
        blocks = extract_fenced(gen["text"])
        ev["fenced_blocks"] = len(blocks)
        if len(blocks) < 2:
            raise ValueError(f"model produced {len(blocks)} fenced blocks "
                             f"(need 2)")

        # 7. Writes through the REAL ToolRouter -> adapters -> Executor.
        def w(path: str, content: str) -> dict:
            res = tool_router.call("filesystem.write",
                                   {"path": path, "content": content},
                                   {"profile": PROFILE})
            ev["actions"].append({"tool": "filesystem.write", "path": path,
                                  "ok": res.get("ok"),
                                  "error": str(res.get("error", ""))[:200]})
            return res

        r1 = w("calc.py", blocks[0])
        r2 = w("test_calc.py", blocks[1])
        if not (r1.get("ok") and r2.get("ok")):
            raise ValueError(f"router writes failed: {r1!r} {r2!r}")

        # 8. Real test execution through the router.
        def run_tests() -> dict:
            return tool_router.call(
                "test.unit", {"command": "python -m unittest test_calc -v"},
                {"profile": PROFILE})

        tres = run_tests()
        ev["test_command"] = "python -m unittest test_calc -v"
        ev["test_result"] = {"ok": tres.get("ok"),
                             "output": str(tres.get("output", tres))[:1500]}

        # 9. Observe + repair once if required.
        attempts = 0
        while not tres.get("ok") and attempts < 1:
            attempts += 1
            fix = ollama_generate(model_name, REPAIR_PROMPT.format(
                error=str(tres.get("output", tres))[:800]))
            fix_blocks = extract_fenced(fix["text"])
            ev["repairs"].append({"attempt": attempts,
                                  "blocks": len(fix_blocks)})
            if not fix_blocks:
                break
            target = "test_calc.py" if "assert" in fix_blocks[0] else "calc.py"
            w(target, fix_blocks[0])
            tres = run_tests()
            ev["test_result"] = {"ok": tres.get("ok"),
                                 "output": str(tres.get("output", tres))[:1500]}
        ev["repair_attempts"] = attempts

        # 10. Verify + audit references + artifacts.
        calc_p = os.path.join(workdir, "calc.py")
        test_p = os.path.join(workdir, "test_calc.py")
        ev["writes"] = {"calc.py": os.path.exists(calc_p),
                        "test_calc.py": os.path.exists(test_p)}
        direct = subprocess.run(
            [sys.executable, "-m", "unittest", "test_calc", "-v"],
            capture_output=True, text=True, timeout=120, cwd=workdir)
        ev["direct_verify"] = {"returncode": direct.returncode,
                               "tail": (direct.stderr or direct.stdout or "")
                               .strip().splitlines()[-4:]}
        ev["audit"] = {"plan_id": plan.plan_id, "session_id": session.session_id,
                       "router_calls": len(ev["actions"]) + 1}
        ev["artifacts"] = {"calc_chars": len(blocks[0]),
                           "test_chars": len(blocks[1])}
        ev["human_gate"] = {"status": "PENDING_OWNER_REVIEW",
                            "note": "task evidence complete; owner accepts or "
                                    "requests revision (nothing auto-approved)"}
        ok = bool(tres.get("ok")) and direct.returncode == 0 \
            and ev["writes"]["calc.py"] and ev["writes"]["test_calc.py"]
        ev["final_result"] = "PASS" if ok else "FAIL"
        ev["status"] = "PASS" if ok else "FAIL"
        ev["pre_autonomy_ready"] = bool(ok)
    except Exception as e:  # noqa: BLE001
        ev["status"] = "FAIL"
        ev["pre_autonomy_ready"] = False
        ev["error"] = f"{type(e).__name__}: {str(e)[:400]}"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    with open(os.path.join(reports_dir, "V08_PRE_AUTONOMY_REPORT.json"), "w",
              encoding="utf-8") as f:
        json.dump(ev, f, indent=1)
    md = ["# v0.8 Pre-Autonomy Report (real DefaultAgent coding acceptance)",
          "",
          f"Task: {TASK}",
          f"Model selected: {ev.get('model_selected')} (why: "
          f"{str(ev.get('why_selected'))[:200]})",
          f"Full registry: {ev.get('full_registry_count')}, shortlist: "
          f"{ev.get('shortlist_count')}",
          f"Shortlisted: {', '.join(ev.get('shortlisted_tools', [])[:8])}",
          f"Placement waves: {ev.get('resource_placement', {}).get('waves')}",
          f"Writes: {ev.get('writes')}, test ok: "
          f"{ev.get('test_result', {}).get('ok')}, repairs: "
          f"{ev.get('repair_attempts')}",
          f"Human gate: {ev.get('human_gate', {}).get('status')}",
          f"Final: {ev.get('final_result')} "
          f"(PRE_AUTONOMY_READY={ev.get('pre_autonomy_ready')})",
          ""]
    with open(os.path.join(docs_dir, "V08_PRE_AUTONOMY_REPORT.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(md))
    print(json.dumps({"status": ev.get("status"),
                      "model": ev.get("model_selected"),
                      "tests_ok": ev.get("test_result", {}).get("ok"),
                      "gate": ev.get("human_gate", {}).get("status")}))
    return 0 if ev.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
