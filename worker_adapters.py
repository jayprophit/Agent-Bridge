"""Worker adapters: the execution hands behind the orchestrator's dispatch.

Each adapter receives a canonical OrchestratorTask (objective + inputs +
acceptance) and returns a structured result dict the orchestrator verifies:

    {"ok": bool, "result": {...}, "changed_files": [...],
     "test_results": {...}, "artifacts": [...], "error": str}

Least privilege: OpenCode sees only its assigned repo/worktree; Ollama sees
only task context; Bridge sees only named capabilities. No worker receives
credentials, KeePass, wallets, or the whole filesystem.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# Role -> installed Ollama model ids (verified live 2026-10-07/08).
OLLAMA_ROLE_MODELS: dict[str, list[str]] = {
    "FAST_LOCAL": ["qwen3:0.6b", "llama3.2:1b-instruct-q4_K_M"],
    "GENERAL_LOCAL": ["qwen3:1.7b", "phi4-mini:latest", "ministral-3:3b",
                      "granite4:3b", "granite3.3:2b"],
    "CODING_LOCAL": ["deepseek-coder:1.3b-instruct-q4_K_M",
                     "qwen2.5-coder:1.5b-instruct-q4_K_M",
                     "qwen2.5-coder:3b-instruct-q4_K_M",
                     "hhao/qwen2.5-coder-tools:3b"],
    "VISION_LOCAL": ["moondream:latest"],
    "EMBEDDING_LOCAL": ["nomic-embed-text:latest"],
}


class WorkerAdapter(ABC):
    worker_id: str = "base"

    @abstractmethod
    def execute(self, task: Any) -> dict[str, Any]:
        """Run the task, return the structured result envelope."""

    def probe(self) -> dict[str, Any]:
        return {"worker_id": self.worker_id, "available": True}


class OpenCodeAdapter(WorkerAdapter):
    """Coding worker via the real `opencode run` surface.

    Receives task contract + repo/worktree + acceptance; returns result +
    changed files + tests + commit SHA where applicable. Never fakes
    autonomous execution: if the CLI cannot run headless here, probe()
    reports the exact limitation and execute() refuses honestly.
    """
    worker_id = "opencode"

    def __init__(self, model: str = "", timeout_s: float = 600.0):
        self.model = model
        self.timeout_s = timeout_s

    def probe(self) -> dict[str, Any]:
        exe = shutil.which("opencode")
        if not exe:
            return {"worker_id": self.worker_id, "available": False,
                    "reason": "opencode not on PATH"}
        try:
            p = subprocess.run([exe, "--version"], capture_output=True,
                               text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as e:
            return {"worker_id": self.worker_id, "available": False,
                    "reason": f"cannot start opencode: {e}"}
        return {"worker_id": self.worker_id, "available": p.returncode == 0,
                "version": (p.stdout or "").strip()[:40]}

    def execute(self, task: Any) -> dict[str, Any]:
        probe = self.probe()
        if not probe["available"]:
            return {"ok": False, "error": f"opencode unavailable: {probe.get('reason')}"}
        workdir = task.worktree or task.repo
        if not workdir:
            return {"ok": False, "error": "opencode task needs repo or worktree"}
        prompt = (f"Task {task.task_id}: {task.objective}\n"
                  f"Allowed paths: {task.allowed_paths}\n"
                  f"Acceptance tests: {task.acceptance_tests}\n"
                  f"Expected artifacts: {task.expected_artifacts}\n"
                  f"Do not touch paths outside allowed_paths.")
        cmd = [shutil.which("opencode"), "run", "--format", "json",
               "--dir", workdir]
        if self.model:
            cmd += ["--model", self.model]
        cmd.append(prompt)
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=self.timeout_s, cwd=workdir)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"opencode timed out after {self.timeout_s}s",
                    "transient": True}
        except OSError as e:
            return {"ok": False, "error": f"cannot start opencode: {e}"}
        return {"ok": p.returncode == 0,
                "result": {"exit_code": p.returncode,
                           "stdout_tail": p.stdout[-4000:],
                           "stderr_tail": p.stderr[-2000:]},
                "changed_files": [], "test_results": {},
                "error": "" if p.returncode == 0 else p.stderr[-500:]}


class OllamaWorkerAdapter(WorkerAdapter):
    """Local model worker via providers.OllamaProvider. Accepts review /
    classify / extract / critique / analyse tasks; response is always a
    structured envelope (parsed JSON when the model cooperates, raw text
    preserved otherwise). FREE_FIRST_STRICT: local only, no cloud."""
    worker_id = "ollama"

    def __init__(self, role: str = "GENERAL_LOCAL", model: str = "",
                 timeout_s: int = 180):
        self.role = role
        self.model = model or OLLAMA_ROLE_MODELS.get(role, ["qwen3:0.6b"])[0]
        self.timeout_s = timeout_s

    def probe(self) -> dict[str, Any]:
        try:
            from providers import OllamaProvider
            prov = OllamaProvider(model=self.model, timeout_s=15)
            models = prov.list_models()
            return {"worker_id": self.worker_id, "available": True,
                    "model": self.model, "fleet_size": len(models),
                    "model_present": self.model in models}
        except Exception as e:
            return {"worker_id": self.worker_id, "available": False,
                    "reason": str(e)[:200]}

    def execute(self, task: Any) -> dict[str, Any]:
        try:
            from providers import OllamaProvider, ProviderError
        except ImportError as e:
            return {"ok": False, "error": f"providers module unavailable: {e}"}
        prov = OllamaProvider(model=self.model, timeout_s=self.timeout_s)
        prompt = (f"You are a {task.role} worker. Task: {task.objective}\n"
                  f"Context: {json.dumps(task.result)[:2000]}\n"
                  f"Reply with a JSON object: "
                  f'{{"verdict": "PASS|FAIL|NEEDS_WORK", "summary": "...", '
                  f'"findings": [...]}}')
        try:
            text = prov.chat([{"role": "user", "content": prompt}])
        except Exception as e:
            return {"ok": False, "error": f"ollama error: {str(e)[:300]}",
                    "transient": True}
        parsed: dict[str, Any] = {}
        try:
            start, end = text.index("{"), text.rindex("}") + 1
            parsed = json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            parsed = {"verdict": "NEEDS_WORK", "summary": text[:1000],
                      "findings": [], "unparsed": True}
        return {"ok": True, "result": parsed, "changed_files": [],
                "test_results": {}, "artifacts": []}


class BridgeWorkerAdapter(WorkerAdapter):
    """Tool/application execution through the existing supervised worker
    architecture (worker_runtime.SupervisedTask). Routes cura-task /
    openmodelica-task / freecad-task assignments; the adapter transports,
    the runtime verifies independently."""
    worker_id = "agent-bridge"

    def __init__(self, root: str | Path, timeout_s: float = 600.0):
        self.root = Path(root).resolve()
        self.timeout_s = timeout_s

    def probe(self) -> dict[str, Any]:
        try:
            from worker_runtime import SupervisedTask
            return {"worker_id": self.worker_id, "available": True,
                    "runtime": "worker_runtime.SupervisedTask"}
        except ImportError as e:
            return {"worker_id": self.worker_id, "available": False,
                    "reason": str(e)[:200]}

    def execute(self, task: Any) -> dict[str, Any]:
        from worker_runtime import SupervisedTask
        kind = (task.result.get("kind") if isinstance(task.result, dict)
                else "") or ""
        assignment = dict(task.result) if isinstance(task.result, dict) else {}
        if kind not in ("cura-task", "openmodelica-task", "freecad-task"):
            return {"ok": False,
                    "error": f"bridge task needs kind cura/openmodelica/freecad, got {kind!r}"}
        worker = SupervisedTask(self.root, task.task_id,
                                worker_id=f"bridge-{task.task_id[:8]}")
        try:
            if kind == "cura-task":
                worker.assign_cura_slice(
                    assignment["stl"], assignment["artifact"],
                    settings=assignment.get("settings", {}),
                    timeout_s=assignment.get("timeout_s", self.timeout_s))
            elif kind == "openmodelica-task":
                worker.assign_openmodelica(
                    assignment["script"], assignment["expected_marker"],
                    assignment["artifact"],
                    timeout_s=assignment.get("timeout_s", self.timeout_s))
            else:
                worker.assign_freecad(
                    assignment["script"], assignment["expected_marker"],
                    assignment["artifact"],
                    timeout_s=assignment.get("timeout_s", self.timeout_s))
            rc = worker.spawn()
            if rc <= 0:
                return {"ok": False, "error": "worker failed to spawn"}
            exit_code = worker.wait(timeout_s=self.timeout_s)
            verdict = worker.verify()
            if exit_code == 0 and verdict.get("verified"):
                out: dict[str, Any] = {"ok": True,
                                       "result": {"verified": True, **verdict},
                                       "changed_files": [], "test_results": {},
                                       "artifacts": [assignment.get("artifact", "")]}
                return out
            return {"ok": False,
                    "error": f"bridge verification failed: {verdict}"}
        finally:
            try:
                worker.cleanup()
            except Exception:
                pass


class OpenClawAdapter(WorkerAdapter):
    """CANDIDATE worker, BLOCKED_OPTIONAL. Never fakes availability: every
    call reports the gateway state honestly so selection skips it and the
    programme continues."""
    worker_id = "openclaw"

    def probe(self) -> dict[str, Any]:
        import socket
        try:
            s = socket.create_connection(("127.0.0.1", 18789), timeout=3)
            s.close()
            return {"worker_id": self.worker_id, "available": True}
        except OSError:
            return {"worker_id": self.worker_id, "available": False,
                    "reason": "BLOCKED_OPTIONAL: gateway stopped, "
                              "owner restart via Companion GUI/tray required"}

    def execute(self, task: Any) -> dict[str, Any]:
        probe = self.probe()
        if not probe["available"]:
            return {"ok": False, "error": probe["reason"],
                    "blocked_optional": True}
        return {"ok": False, "error": "openclaw execution path not yet mapped",
                "blocked_optional": True}
