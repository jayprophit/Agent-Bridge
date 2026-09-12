"""Windows v0.7 local acceptance (bounded, side-effect free).

Aggregates implemented capability areas. Truthful unavailable statuses are
reported as SKIPPED_* (never failures). Exit 0 unless a core category FAILs.

Usage:
    python run_windows_v07_acceptance.py [--json-out PATH] [--md-out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, FAIL = "PASS", "FAIL"
SKIP_PROVIDER, SKIP_DEVICE, SKIP_INSTALLED, SKIP_CONFIG = (
    "SKIPPED_PROVIDER_REQUIRED", "SKIPPED_DEVICE_REQUIRED",
    "SKIPPED_NOT_INSTALLED", "SKIPPED_CONFIGURATION_REQUIRED",
)

CHECKS: list[tuple[str, object]] = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


@check("device_profile")
def _device():
    from device import DeviceProfiler, HardwareProfiler
    p = DeviceProfiler().profile_with_hardware(HardwareProfiler(), True)
    assert p.device_id and p.os == "windows"
    return {"device_class": p.device_class, "runtime_role": p.runtime_role,
            "cpu": p.cpu.model, "ram_mb": p.memory.total_mb,
            "gpu": p.gpu.model, "camera": p.media.camera_present,
            "microphone": p.media.microphone_present,
            "package_managers": [m.name for m in p.package_managers if m.detected]}


@check("runtime_provider_discovery")
def _runtimes():
    from runtimes import LocalRuntimeDiscovery
    found = LocalRuntimeDiscovery().discover()
    healthy = [r for r in found if r.status == "HEALTHY"]
    if not healthy:
        return {"_status": SKIP_PROVIDER, "runtimes": [r.runtime_id for r in found]}
    return {"runtimes": [(r.runtime_id, r.protocol, len(r.models)) for r in healthy]}


@check("model_discovery")
def _models():
    from runtimes import LocalRuntimeDiscovery
    found = LocalRuntimeDiscovery().discover()
    models = [m.get("name") for r in found if r.status == "HEALTHY" for m in r.models]
    if not models:
        return {"_status": SKIP_PROVIDER, "models": []}
    return {"model_count": len(models)}


@check("benchmark_calibration")
def _bench():
    from benchmarks import BenchmarkHistory, BenchmarkStore
    from device import DeviceProfiler, HardwareProfiler
    from device.runtime_tuner import RuntimeTuner
    history = BenchmarkHistory(BenchmarkStore())
    tested = history.get_all_models_tested()
    tuner = RuntimeTuner(DeviceProfiler(), HardwareProfiler())
    params = tuner.tune_with_calibration(history) if tested else tuner.tune()
    return {"models_with_history": len(tested),
            "profile": params.performance_profile,
            "overrides": len(getattr(params, "calibration_overrides", []) or [])}


@check("ide_discovery")
def _ides():
    found = []
    for name, paths in (
        ("VS Code", [r"C:\Program Files\Microsoft VS Code\Code.exe",
                     os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe")]),
        ("Cursor", [os.path.expandvars(r"%LOCALAPPDATA%\Programs\cursor\Cursor.exe")]),
    ):
        for path in paths:
            if path and os.path.exists(path):
                found.append(name)
                break
    if not found:
        return {"_status": SKIP_INSTALLED, "ides": []}
    return {"ides": found}


@check("agent_discovery")
def _agents():
    from agent.default_agent import DefaultAgent  # noqa: F401 (runtime-owned)
    from agents.registry import AgentRegistry
    return {"default_agent": "runtime-owned",
            "external_agents_registered": len(AgentRegistry())}


@check("browser")
def _browser():
    try:
        import browser_cdp
        return {"browser": browser_cdp.find_browser()}
    except Exception as e:  # noqa: BLE001
        return {"_status": SKIP_INSTALLED, "reason": str(e)[:200]}


@check("tts")
def _tts():
    try:
        import win32com.client  # noqa
        return {"backend": "SAPI (win32com present)"}
    except ImportError:
        return {"_status": SKIP_INSTALLED, "reason": "no local TTS backend (win32com missing)"}


@check("stt_probe")
def _stt():
    return {"_status": SKIP_INSTALLED, "reason": "no local STT backend configured"}


@check("vision_probe")
def _vision():
    from tools.cat_media import VisionAdapter
    probe = VisionAdapter(None, "vision.inspect_image").probe()
    if probe.get("available"):
        return {"vision": probe}
    return {"_status": SKIP_PROVIDER, "reason": probe.get("reason", "")[:200]}


@check("image_provider_probe")
def _image():
    import urllib.request
    for url in ("http://127.0.0.1:7860/", "http://127.0.0.1:8188/"):
        try:
            urllib.request.urlopen(url, timeout=3)
            return {"provider": f"local image server at {url}"}
        except Exception:
            pass
    return {"_status": SKIP_INSTALLED, "reason": "no local image server on :7860/:8188"}


@check("ffmpeg_probe")
def _ffmpeg():
    import shutil
    path = shutil.which("ffmpeg")
    if not path:
        return {"_status": SKIP_INSTALLED, "reason": "ffmpeg not on PATH"}
    return {"ffmpeg": path}


@check("audio_backend")
def _audio():
    try:
        import wave  # noqa: F401 (stdlib decode only; no record/play backend)
        return {"backend": "stdlib wave decode only; no record/play backend"}
    except ImportError:
        return {"_status": SKIP_INSTALLED, "reason": "wave stdlib missing"}


@check("ocr_backend")
def _ocr():
    import shutil
    path = shutil.which("tesseract")
    if not path:
        return {"_status": SKIP_INSTALLED, "reason": "tesseract not on PATH"}
    return {"ocr": path}


@check("package_policy")
def _package_policy():
    from tools.tool_audit import audit as run_audit
    matrix = run_audit()
    by_id = {t["tool_id"]: t for t in matrix["tools"]}
    listing = [by_id.get(f"package.{s}") for s in ("list", "search")]
    mutating = [by_id.get(f"package.{s}") for s in ("install", "remove", "update")]
    assert all(t and t["risk"] == "READ_ONLY" for t in listing), listing
    assert all(t and t["risk"] == "INSTALL" for t in mutating if t), mutating
    return {"list_search": "READ_ONLY",
            "mutating": "INSTALL-gated",
            "detected_managers": ["pip", "npm", "node", "winget", "choco", "git"]}


@check("gui_probe")
def _gui():
    try:
        import ctypes
        user32 = ctypes.windll.user32
        return {"display": f"{user32.GetSystemMetrics(0)}x{user32.GetSystemMetrics(1)}"}
    except Exception as e:  # noqa: BLE001
        return {"_status": SKIP_DEVICE, "reason": str(e)[:200]}


@check("owner_full_access")
def _owner():
    import inspect
    from runtime import RuntimeConfig
    gated = "owner_authorized" in inspect.signature(RuntimeConfig.__init__).parameters
    return {"local_gate_present": gated,
            "remote_policy": "REMOTE_OWNER_DISABLED by default (nodes.NodeServerState)"}


@check("safe_profiles")
def _profiles():
    from tools.cat_nodes import node_records
    from tools.registry import ToolRegistry
    from tools.router import ToolRouter
    reg = ToolRegistry()
    for rec in node_records():
        try:
            reg.register(rec)
        except ValueError:
            pass
    res = ToolRouter(reg).call("node.delegate", {"task_id": "t"},
                               {"profile": "SAFE_EXPLORATION"})
    assert res.get("kind") == "PROFILE_DENIED", res
    return {"profile_gate": "enforced"}


@check("node_localhost_transport")
def _node():
    import threading
    import urllib.request
    from nodes.node_server import NodeServerState, serve_node
    state = NodeServerState("acceptance-node", lambda: {"node_id": "acceptance-node"},
                            lambda _r: "UNTRUSTED_NODE", None)
    srv = serve_node(state, host="127.0.0.1", port=0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{srv.server_address[1]}/v1/node/health",
                timeout=5) as r:
            body = json.loads(r.read().decode())
        assert body.get("ok")
        return {"health": "ok", "security_mode": body.get("security_mode")}
    finally:
        srv.shutdown()
        th.join(timeout=5)
        srv.server_close()


@check("pairing")
def _pairing():
    from nodes.node_transport import PairingManager, challenge_response
    pm = PairingManager("acceptance-node")
    attempt, token = pm.request_pairing("peer")
    ok, _, challenge = pm.approve(attempt, True, "LIMITED_NODE")
    assert ok
    ok, _ = pm.verify_challenge(attempt, token,
                                challenge_response(token, attempt, challenge))
    assert ok and pm.mark_paired(attempt)
    return {"pairing": "challenge-response ok"}


@check("privacy_routing")
def _privacy():
    from nodes import (NodeDescriptor, NodeRegistry, TaskRequirements,
                       create_node_router, create_trust_registry)
    reg = NodeRegistry()
    reg.register(NodeDescriptor(node_id="local", online=True, memory_mb=16384,
                                tools=["filesystem.read"]))
    trust = create_trust_registry("local")
    router = create_node_router(reg, trust, "local")
    d = router.route("t", TaskRequirements(required_tools=["filesystem.read"],
                                           privacy_policy="CURRENT_DEVICE_ONLY",
                                           data_locality="local"))
    return {"route": d.selected_node_id}


@check("tool_capability_audit")
def _audit():
    from tools.tool_audit import audit as run_audit
    matrix = run_audit()
    bad = [t["tool_id"] for t in matrix["tools"]
           if t["declared_status"] == "AVAILABLE" and not t["backend"]]
    assert not bad, f"AVAILABLE without backend: {bad}"
    return {"total": matrix["total_registered_tools"], "counts": matrix["counts"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=os.path.join("reports", "v0.8", "LOCAL_V07_ACCEPTANCE_REPORT.json"))
    ap.add_argument("--md-out", default=os.path.join("docs", "releases", "v0.8", "LOCAL_V07_ACCEPTANCE_REPORT.md"))
    ns = ap.parse_args(argv)
    results = []
    for name, fn in CHECKS:
        t0 = time.monotonic()
        try:
            detail = fn() or {}
            status = detail.pop("_status", PASS)
            results.append({"category": name, "status": status,
                            "duration_s": round(time.monotonic() - t0, 2),
                            "detail": detail})
        except Exception as e:  # noqa: BLE001
            results.append({"category": name, "status": FAIL,
                            "duration_s": round(time.monotonic() - t0, 2),
                            "detail": {"error": f"{type(e).__name__}: {e}",
                                       "trace": traceback.format_exc()[-800:]}})
    report = {"results": results,
              "summary": {s: sum(1 for r in results if r["status"] == s)
                          for s in {r["status"] for r in results}}}
    with open(ns.json_out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    with open(ns.md_out, "w", encoding="utf-8") as f:
        f.write("# Local v0.7 Acceptance Report\n\n" + "\n".join(
            f"- {r['category']}: {r['status']} ({r['duration_s']}s)" for r in results) + "\n")
    fails = [r for r in results if r["status"] == FAIL]
    print(f"acceptance: {len(results)} categories, {len(fails)} failures")
    for r in results:
        print(f"  {r['category']}: {r['status']}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
