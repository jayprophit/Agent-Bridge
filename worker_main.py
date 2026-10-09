"""Canonical worker entrypoint: the program a supervised worker process runs.

This is deliberately a *bounded* worker, not a general agent. It reads exactly
one assignment file (task.json) from the directory it was started with, and it
may touch only the paths that assignment names. Everything it produces --
heartbeats, checkpoints, result, artifacts -- goes back into that same
directory, where the supervisor observes it without ever entering the process.

The worker holds no authority: no policy engine, no grants, no network, no
knowledge of any other task. It cannot approve, merge, publish or escalate.
Consequential effects remain subject to P25 outside this process.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    """Atomic JSON write: a supervisor reading concurrently must see either
    the whole previous heartbeat or the whole new one, never a torn file that
    parses as nothing and looks like a dead worker."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def _fail(task_dir: Path, code: str, message: str) -> int:
    _write_json(task_dir / "result.json", {
        "ok": False, "error_code": code, "error": message,
        "finished_at": time.time(),
    })
    return 1


def _heartbeat(task_dir: Path, seq: int, state: str) -> None:
    _write_json(task_dir / "heartbeat.json", {
        "seq": seq, "state": state, "at": time.time(),
    })


def _checkpoint(task_dir: Path, done: int, total: int) -> None:
    _write_json(task_dir / "checkpoint.json", {
        "lines_done": done, "lines_total": total, "at": time.time(),
    })


def main(task_dir: str) -> int:
    root = Path(task_dir).resolve()
    try:
        assignment = json.loads((root / "task.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"worker: cannot read assignment: {e}", file=sys.stderr)
        return 2
    if assignment.get("kind") != "transform-lines":
        if assignment.get("kind") == "model-query":
            return _run_model_query(root, assignment)
        if assignment.get("kind") == "freecad-task":
            return _run_freecad_task(root, assignment)
        if assignment.get("kind") == "cura-task":
            return _run_cura_task(root, assignment)
        if assignment.get("kind") == "openmodelica-task":
            return _run_openmodelica_task(root, assignment)
        return _fail(root, "unknown-task-kind", f"unsupported task kind {assignment.get('kind')!r}")

    try:
        rel_in = Path(assignment["input"]).as_posix()
        rel_out = Path(assignment["output"]).as_posix()
    except (KeyError, TypeError):
        return _fail(root, "bad-assignment", "task needs input and output paths")
    # Containment: the assignment may name only paths inside the task dir.
    # Anything else is refused before any file is touched.
    for rel in (rel_in, rel_out):
        if rel.startswith("/") or ".." in Path(rel).parts or Path(rel).is_absolute():
            return _fail(root, "path-escape", f"assignment path escapes the task dir: {rel!r}")
    src, dst = root / rel_in, root / rel_out
    try:
        lines = src.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return _fail(root, "input-unreadable", str(e))

    mode = assignment.get("mode", "sort-unique")
    if mode != "sort-unique":
        return _fail(root, "unknown-mode", f"unsupported mode {mode!r}")

    total = len(lines)
    out: list[str] = []
    seen: set[str] = set()
    _heartbeat(root, 0, "running")
    _checkpoint(root, 0, total)
    # Heartbeats are time-based, not per-line: 12,000 tiny files for a large
    # input is filesystem abuse that can get the process throttled or killed
    # by on-access scanners, which would look exactly like worker failure.
    last_beat = time.time()
    for i, line in enumerate(sorted(lines)):
        if line not in seen:
            seen.add(line)
            out.append(line)
        # A real long task checkpoints as it goes; a killed worker therefore
        # always leaves a truthful record of how far it got.
        now = time.time()
        if now - last_beat >= 0.5 or (i + 1) == total:
            _heartbeat(root, i + 1, "running")
            _checkpoint(root, i + 1, total)
            last_beat = now
    # Bytes, not text: on Windows a text write would translate newlines and the
    # file would no longer match the digest computed above. The digest must
    # describe the world exactly as it lands.
    payload = ("\n".join(out) + "\n").encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    try:
        dst.write_bytes(payload)
    except OSError as e:
        return _fail(root, "output-unwritable", str(e))
    _heartbeat(root, total + 1, "done")
    _write_json(root / "result.json", {
        "ok": True, "lines_in": total, "lines_out": len(out),
        "output_digest": digest, "finished_at": time.time(),
    })
    return 0


def _query_model(endpoint: str, model: str, prompt: str, timeout_s: float) -> str:
    """Ask the model backend one question through the canonical provider.

    The weights are leased EPHEMERAL: this worker is a short-lived process
    that must not leave a model resident when it exits, so the lease is
    released the moment the call returns (§consolidation). The backend is an
    external program (Ollama server + model weights); residency of that
    program is the provider layer's responsibility, not the worker's.
    """
    from compute.ollama_provider_v2 import LeasePolicy, OllamaProviderV2
    provider = OllamaProviderV2(base_url=endpoint.rstrip("/"),
                                timeout=timeout_s)
    try:
        data = provider.infer(model, prompt, policy=LeasePolicy.EPHEMERAL)
    except Exception as e:  # noqa: BLE001 -- transport failure is a task failure
        raise RuntimeError(f"model backend unreachable: {e}")
    answer = data.get("response", "")
    if not isinstance(answer, str):
        raise RuntimeError("model backend returned a malformed response")
    return answer.strip()


def _run_model_query(root: Path, assignment: dict) -> int:
    try:
        questions = assignment["questions"]
        model = assignment["model"]
        rel_out = Path(assignment["output"]).as_posix()
    except (KeyError, TypeError):
        return _fail(root, "bad-assignment", "model-query needs questions, model and output")
    if not isinstance(questions, list) or not questions:
        return _fail(root, "bad-assignment", "model-query needs a non-empty question list")
    if rel_out.startswith("/") or ".." in Path(rel_out).parts or Path(rel_out).is_absolute():
        return _fail(root, "path-escape", f"assignment path escapes the task dir: {rel_out!r}")
    endpoint = assignment.get("endpoint", "http://127.0.0.1:11434")
    timeout_s = float(assignment.get("per_question_timeout_s", 120.0))
    answers: dict[str, str] = {}
    total = len(questions)
    _heartbeat(root, 0, "running")
    _checkpoint(root, 0, total)
    for i, question in enumerate(questions):
        qid = question.get("id", f"q{i}")
        try:
            answers[qid] = _query_model(endpoint, model, question.get("prompt", ""), timeout_s)
        except RuntimeError as e:
            return _fail(root, "model-failed", f"{qid}: {e}")
        _heartbeat(root, i + 1, "running")
        _checkpoint(root, i + 1, total)
    payload = json.dumps(answers, indent=2, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    try:
        (root / rel_out).write_bytes(payload)
    except OSError as e:
        return _fail(root, "output-unwritable", str(e))
    _heartbeat(root, total + 1, "done")
    _write_json(root / "result.json", {
        "ok": True, "questions": total,
        "output_digest": digest, "finished_at": time.time(),
        "model": model, "endpoint": endpoint,
    })
    return 0


def _run_freecad_task(root: Path, assignment: dict) -> int:
    """Execute a supervisor-approved FreeCAD script through the canonical
    application adapter. The worker does not choose the script, the paths or
    the budget: all three arrive in the signed assignment. The adapter
    enforces its own containment; this function only transports."""
    import freecad_adapter
    try:
        script = Path(assignment["script"]).as_posix()
        timeout_s = float(assignment.get("timeout_s", 300.0))
    except (KeyError, TypeError, ValueError):
        return _fail(root, "bad-assignment", "freecad-task needs script and timeout_s")
    if script.startswith("/") or ".." in Path(script).parts or Path(script).is_absolute():
        return _fail(root, "path-escape", f"assignment path escapes the task dir: {script!r}")
    _heartbeat(root, 0, "running")
    discovery = freecad_adapter.discover()
    if not discovery.found:
        return _fail(root, "app-missing", f"FreeCAD unavailable: {discovery.reason}")
    _heartbeat(root, 1, "running")
    result = freecad_adapter.run_script(discovery.executable, root / script, root, timeout_s)
    _heartbeat(root, 2, "done" if result.ok else "failed")
    payload = json.dumps({
        "ok": result.ok, "exit_code": result.exit_code,
        "stdout_tail": result.stdout_tail, "stderr_tail": result.stderr_tail,
        "elapsed_s": round(result.elapsed_s, 1), "timed_out": result.timed_out,
        "finished_at": time.time(),
    }, indent=2).encode("utf-8")
    (root / "result.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (root / "result.sha256").write_text(digest, encoding="utf-8")
    return 0 if result.ok else 1


def _run_cura_task(root: Path, assignment: dict) -> int:
    """Slice a supervisor-approved STL through the canonical Cura adapter.

    The worker does not choose the mesh, the settings or the budget: all
    arrive in the signed assignment. Printer definitions are resolved from
    the discovered installation (shipped fdmprinter/fdmextruder), never
    from caller-supplied absolute paths outside the task dir.
    """
    import cura_adapter
    try:
        stl = Path(assignment["stl"]).as_posix()
        artifact = Path(assignment["artifact"]).as_posix()
        settings = assignment.get("settings") or {}
        timeout_s = float(assignment.get("timeout_s", 300.0))
    except (KeyError, TypeError, ValueError):
        return _fail(root, "bad-assignment", "cura-task needs stl, artifact and timeout_s")
    for rel in (stl, artifact):
        if rel.startswith("/") or ".." in Path(rel).parts or Path(rel).is_absolute():
            return _fail(root, "path-escape", f"assignment path escapes the task dir: {rel!r}")
    if not isinstance(settings, dict):
        return _fail(root, "bad-assignment", "cura-task settings must be an object")
    _heartbeat(root, 0, "running")
    discovery = cura_adapter.discover()
    if not discovery.found:
        return _fail(root, "app-missing", f"CuraEngine unavailable: {discovery.reason}")
    share = Path(discovery.executable).parent / "share" / "cura" / "resources" / "definitions"
    printer, extruder = share / "fdmprinter.def.json", share / "fdmextruder.def.json"
    if not (printer.is_file() and extruder.is_file()):
        return _fail(root, "app-missing", f"Cura printer definitions absent under {share}")
    _heartbeat(root, 1, "running")
    result = cura_adapter.slice_stl(discovery.executable, root / stl, root / artifact,
                                    root, printer, extruder, settings, timeout_s)
    _heartbeat(root, 2, "done" if result.ok else "failed")
    payload = json.dumps({
        "ok": result.ok,
        "layers": result.layers, "g1_moves": result.g1_moves,
        "stdout_tail": "", "stderr_tail": result.stderr_tail,
        "elapsed_s": round(result.elapsed_s, 1), "timed_out": result.timed_out,
        "finished_at": time.time(),
    }, indent=2).encode("utf-8")
    (root / "result.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (root / "result.sha256").write_text(digest, encoding="utf-8")
    return 0 if result.ok else 1


def _run_openmodelica_task(root: Path, assignment: dict) -> int:
    """Execute a supervisor-approved .mos script through the canonical
    OpenModelica adapter. Same transport discipline as the FreeCAD seam:
    the worker carries the approved script to the adapter and reports the
    transcript; authorization and verification stay outside this process."""
    import openmodelica_adapter
    try:
        script = Path(assignment["script"]).as_posix()
        timeout_s = float(assignment.get("timeout_s", 600.0))
    except (KeyError, TypeError, ValueError):
        return _fail(root, "bad-assignment", "openmodelica-task needs script and timeout_s")
    if script.startswith("/") or ".." in Path(script).parts or Path(script).is_absolute():
        return _fail(root, "path-escape", f"assignment path escapes the task dir: {script!r}")
    _heartbeat(root, 0, "running")
    discovery = openmodelica_adapter.discover()
    if not discovery.found:
        return _fail(root, "app-missing", f"OpenModelica unavailable: {discovery.reason}")
    _heartbeat(root, 1, "running")
    result = openmodelica_adapter.run_mos(discovery.executable, root / script, root, timeout_s)
    _heartbeat(root, 2, "done" if result.ok else "failed")
    payload = json.dumps({
        "ok": result.ok, "exit_code": result.exit_code,
        "stdout_tail": result.stdout_tail, "stderr_tail": result.stderr_tail,
        "elapsed_s": round(result.elapsed_s, 1), "timed_out": result.timed_out,
        "finished_at": time.time(),
    }, indent=2).encode("utf-8")
    (root / "result.json").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    (root / "result.sha256").write_text(digest, encoding="utf-8")
    return 0 if result.ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: worker_main.py <task-dir>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
