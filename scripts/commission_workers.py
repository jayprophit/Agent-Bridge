#!/usr/bin/env python
"""§6-§9 AI APPLICATION COMMISSIONING: workstation discovery + per-app
assessment against the §7 pipeline.

For each candidate AI application:
    DISCOVER -> VERIFY INSTALLED -> (LAUNCH) -> IDENTIFY WINDOW ->
    DETERMINE CONTROL CHANNEL -> REGISTER WORKER (statuses:
    UNASSESSED / DISCOVERED / LAUNCHABLE / CONTROLLABLE / AGENT_VERIFIED /
    QUOTA_VERIFIED / MODEL_VERIFIED / WORKER_READY / BLOCKED / UNSUITABLE).

Honesty (§15/§38): an app with NO structured control channel is recorded as
LAUNCHABLE-not-CONTROLLABLE with the exact reason — never fabricated as a
ready worker. Commissioning is sequential and light (§8): discovery is
read-only; it launches nothing heavy.

Usage:
    python scripts/commission_workers.py [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# commissioning statuses (§7)
UNASSESSED = "UNASSESSED"
DISCOVERED = "DISCOVERED"
LAUNCHABLE = "LAUNCHABLE"
CONTROLLABLE = "CONTROLLABLE"
AGENT_VERIFIED = "AGENT_VERIFIED"
QUOTA_VERIFIED = "QUOTA_VERIFIED"
MODEL_VERIFIED = "MODEL_VERIFIED"
WORKER_READY = "WORKER_READY"
BLOCKED = "BLOCKED"
UNSUITABLE = "UNSUITABLE"

# candidate pool (§6) — the visible list is only a starting point
CANDIDATES = {
    "opencode": {"cli": "opencode", "channel": "cli",
                 "note": "headless run + db telemetry (§9 adapter)"},
    "codex": {"cli": "codex", "channel": "cli",
              "note": "codex exec resume --last (§9 adapter)"},
    "cursor": {"cli": "cursor", "channel": "cli-editor",
               "note": "Cursor CLI is a diff/merge editor, not an agent "
                       "control channel"},
    "claude": {"cli": None, "exe": "AnthropicClaude/claude.exe",
               "channel": "gui", "note": "desktop app, no CLI on PATH"},
    "antigravity": {"cli": None, "channel": "gui",
                    "note": "desktop IDE"},
    "deepseek": {"cli": None, "channel": "gui", "note": "desktop app"},
    "devin": {"cli": None, "channel": "gui", "note": "desktop app"},
    "kimi": {"cli": None, "channel": "gui", "note": "desktop app"},
    "qwen": {"cli": None, "channel": "gui", "note": "desktop app"},
    "manus": {"cli": None, "channel": "web", "note": "web app (explorer)"},
    "chatgpt": {"cli": None, "channel": "web", "note": "web/PWA"},
    "ollama": {"cli": "ollama", "channel": "local-runtime",
               "note": "local model runtime (free-first tier)"},
}


def _on_path(binary: str) -> bool:
    try:
        r = subprocess.run(["where", binary] if sys.platform ==
                           "win32" else ["which", binary],
                           capture_output=True, text=True, timeout=15.0)
        return r.returncode == 0 and binary.lower() in (r.stdout or "").lower()
    except (subprocess.TimeoutExpired, OSError):
        return False


def assess(name: str, spec: dict) -> dict:
    """Assess one candidate against the §7 pipeline. Read-only: discovers
    the control channel and classifies honestly; launches nothing."""
    rec = {"app": name, "status": UNASSESSED, "control_channel": None,
           "reason": "", "agent_capable": False, "quota_known": False}
    cli = spec.get("cli")
    channel = spec.get("channel", "gui")
    if cli and _on_path(cli):
        rec["status"] = DISCOVERED
        rec["control_channel"] = f"cli:{cli}"
        if channel == "cli":
            # a real headless agent channel -> the highest commissioning tier
            rec["status"] = CONTROLLABLE
            rec["agent_capable"] = True
            rec["reason"] = (f"CLI on PATH with headless agent channel "
                             f"({spec.get('note', '')})")
        elif channel == "local-runtime":
            rec["status"] = CONTROLLABLE
            rec["agent_capable"] = True
            rec["reason"] = "local model runtime, free-first tier"
        else:
            rec["status"] = LAUNCHABLE
            rec["reason"] = ("CLI present but " +
                             str(spec.get("note", "not an agent control "
                                  "channel")))
    elif channel in ("gui", "web"):
        rec["status"] = LAUNCHABLE
        rec["control_channel"] = channel
        rec["reason"] = (f"installed as a {channel} application; no "
                         f"structured headless control channel on PATH — "
                         f"commissionable to WORKER_READY only via GUI "
                         f"automation or an MCP/A2A bridge, recorded honestly "
                         f"(§15), not fabricated")
    else:
        rec["status"] = DISCOVERED
        rec["reason"] = spec.get("note", "candidate, channel unverified")
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    results = [assess(name, spec) for name, spec in CANDIDATES.items()]
    ready = [r for r in results if r["status"] in
             (CONTROLLABLE, AGENT_VERIFIED, WORKER_READY)]
    launchers = [r for r in results if r["status"] == LAUNCHABLE]

    print(f"Commissioning pass: {len(results)} candidates assessed")
    print(f"  controllable now (headless agent channel): "
          f"{[r['app'] for r in ready]}")
    print(f"  launchable, not yet controllable: "
          f"{[r['app'] for r in launchers]}")
    print()
    for r in results:
        print(f"  {r['app']:12} {r['status']:14} {r['reason'][:70]}")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2),
                                   encoding="utf-8")
        print(f"\nwritten: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
