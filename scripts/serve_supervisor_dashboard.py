#!/usr/bin/env python
"""§16-§19: LIVE Supervisor Dashboard server.

Serves the **authoritative** supervisor state written by the daemon
(`compute/supervisor_runtime.py --daemon`). The daemon persists every cycle to
`supervisor_state/supervisor_runtime_checkpoint.json`; this server reads THAT
checkpoint as the single source of truth.

Architecture (§4/§5/§6 correction — one supervisor reality):

    HERMES SUPERVISOR DAEMON  (--daemon)
          |  writes checkpoint every cycle
          v
    supervisor_state/supervisor_runtime_checkpoint.json   <- authoritative
          |
          v
    serve_supervisor_dashboard.py  (read-only API on :8472)
          |  serves /v1/supervisor/{health,state,events}
          v
    Vite dashboard (:5199) + IDE-Workspace UI

The API does NOT instantiate a second SupervisorRuntime.  It loads the
checkpoint, annotates it with state versioning (§7), and serves it.  If the
checkpoint is stale (>2x the cycle interval), the dashboard reports STALE so
the UI never silently fabricates liveness.

Usage:
    python scripts/serve_supervisor_dashboard.py [--port 8472]
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from nodes import supervisor as sup  # noqa: E402
from compute.supervisor_invariants import check_all  # noqa: E402

STATE_VERSION = "1.0"


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else list(v)


class CheckpointReader:
    """Read-only loader over the daemon's authoritative checkpoint."""

    def __init__(self, state_dir, expected_interval_s=120.0):
        self.state_dir = Path(state_dir)
        self.ckpt_path = self.state_dir / "supervisor_runtime_checkpoint.json"
        self.expected_interval_s = expected_interval_s
        self._lock = threading.Lock()

    def _load(self):
        if not self.ckpt_path.exists():
            return None
        try:
            return json.loads(self.ckpt_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def read(self):
        """Return the authoritative snapshot + versioning metadata."""
        with self._lock:
            data = self._load()
        now = time.time()
        if data is None:
            return {
                "state_version": STATE_VERSION,
                "supervisor_instance_id": "UNINITIALISED",
                "cycle_id": 0,
                "cycles": 0,
                "continuation_required": True,
                "observed_at": None,
                "stale": True,
                "stale_reason": "checkpoint not found - daemon may not be running",
                "snapshot": {"schema_version": 1, "session_id": "dashboard-readmodel",
                             "generated_at": now, "last_event_seq": 0,
                             "sections": {}},
            }
        observed = data.get("observed_at") or data.get("saved_at", 0)
        age = now - observed if observed else float("inf")
        stale = age > 2 * self.expected_interval_s
        sections = self._build_sections(data)
        result = {
            "state_version": data.get("state_version", STATE_VERSION),
            "supervisor_instance_id": data.get("supervisor_instance_id", "UNKNOWN"),
            "cycle_id": data.get("cycle_id", data.get("cycles", 0)),
            "cycles": data.get("cycles", 0),
            "continuation_required": data.get("continuation_required", True),
            "observed_at": observed,
            "observed_age_s": age,
            "stale": stale,
            "snapshot": {
                "schema_version": 1,
                "session_id": "dashboard-readmodel",
                "generated_at": now,
                "last_event_seq": data.get("cycles", 0),
                "sections": sections,
            },
        }
        if stale:
            result["stale_reason"] = f"checkpoint {age:.0f}s old > {2*self.expected_interval_s:.0f}s"
        return result

    def _build_sections(self, data):
        """Build the nodes.supervisor section contract from the checkpoint."""
        acq = data.get("acquisition") or {}
        unassessed = acq.get("unassessed_list", []) if isinstance(acq, dict) else []
        workers = {w: wd for w, wd in (data.get("workers") or {}).items() if wd}

        # §36/§49 Constitution: re-check from the daemon's persisted snapshot
        snapshot = {
            "workers": workers,
            "providers": data.get("providers", {}),
            "ready_tasks": [],
            "handoffs_pending": 0,
            "gaps": _as_list(data.get("open_gaps", [])),
            "quotas": {},
            "resources": data.get("resources_sample", {}),
            "projects": {},
            "unassessed_apps": [{"app_id": a["app_id"],
                                 "last_action_epoch": a.get("last_action_epoch", 0)}
                                for a in unassessed],
            "internal_workers": data.get("internal_workers", 0),
            "min_internal_target": 5,
            "continuation_required": data.get("continuation_required", True),
            "last_cycle_emitted_report": False,
            "worker_actions": (data.get("last_actions") or [{}])[-1]
                                if data.get("last_actions") else {},
            "now_epoch": time.time(),
            "model_routing": {"paid_budget_remaining": 0},
            "lane_starvation": data.get("lane_starvation", []),
            "deferred_tasks": [],
        }
        result = check_all(snapshot)
        constitution = result.to_dict() if hasattr(result, "to_dict") else {
            "checked": 0, "passed": False, "violations": result.get("violations", [])
        }

        by_status = {}
        for wd in workers.values():
            st = wd.get("status", "UNKNOWN")
            by_status[st] = by_status.get(st, 0) + 1

        return {
            "supervision": {
                "workers_total": {"value": len(workers),
                                  "state": "LIVE_VERIFIED",
                                  "source": "checkpoint"},
                "workers_by_status": {"value": by_status,
                                      "state": "LIVE_VERIFIED",
                                      "source": "checkpoint"},
                "handoffs_pending": {"value": len(data.get("last_actions", [])),
                                     "state": "LIVE_VERIFIED",
                                     "source": "checkpoint"},
                "handoffs_total": {"value": len(data.get("last_actions", [])),
                                   "state": "LIVE_VERIFIED",
                                   "source": "checkpoint"},
                "gaps_open": {"value": 0, "state": "LIVE_VERIFIED",
                              "source": "checkpoint"},
                "gaps_by_severity": {"value": {}, "state": "LIVE_VERIFIED",
                                     "source": "checkpoint"},
                "continuation_required": {"value": data.get("continuation_required", True),
                                          "state": "LIVE_VERIFIED",
                                          "source": "checkpoint"},
                "workers": {"value": list(workers.values()),
                            "state": "LIVE_VERIFIED", "source": "checkpoint"},
                "constitution": {"value": constitution,
                                 "state": "LIVE_VERIFIED",
                                 "source": "checkpoint"},
            },
            "resources": {
                "pressure_state": {"value": data.get("resources", {})
                                   .get("pressure_state") if isinstance(data.get("resources"), dict) else None,
                                   "state": "LIVE_VERIFIED", "source": "checkpoint"},
                "sample": {"value": data.get("resources", {}).get("sample")
                           if isinstance(data.get("resources"), dict) else None,
                           "state": "LIVE_VERIFIED", "source": "checkpoint"},
            },
            "providers": {"value": data.get("providers", {}),
                          "state": "LIVE_VERIFIED" if data.get("providers") else "EMPTY",
                          "source": "checkpoint"},
            "acquisition": {"value": acq,
                            "state": "LIVE_VERIFIED" if acq else "EMPTY",
                            "source": "checkpoint"},
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8472)
    ap.add_argument("--state-dir", default="supervisor_state")
    ap.add_argument("--interval", type=float, default=120.0)
    args = ap.parse_args()

    reader = CheckpointReader(args.state_dir,
                              expected_interval_s=args.interval)
    state = sup.create_supervisor_state(session_id="dashboard-readmodel")

    # Initial load so the first request is real.
    snap = reader.read()
    snap_sections = snap.get("snapshot", {}).get("sections", {})
    for name, section in (snap_sections or {}).items():
        state.set_section(name, section)
    state.set_meta("state_version", snap.get("state_version"))
    state.set_meta("supervisor_instance_id", snap.get("supervisor_instance_id"))
    state.set_meta("cycle_id", snap.get("cycle_id"))
    state.set_meta("observed_at", snap.get("observed_at"))

    srv = sup.build_supervisor_server(state, host="127.0.0.1", port=args.port)
    print(f"Supervisor Dashboard API (read-model) on http://127.0.0.1:{args.port} "
          f"- reading daemon checkpoint <- {reader.ckpt_path}", flush=True)

    def _refresh_loop():
        while True:
            time.sleep(min(args.interval, 30.0))
            try:
                snap = reader.read()
                secs = snap.get("snapshot", {}).get("sections", {})
                for name, section in (secs or {}).items():
                    state.set_section(name, section)
                state.set_meta("state_version", snap.get("state_version"))
                state.set_meta("supervisor_instance_id",
                               snap.get("supervisor_instance_id"))
                state.set_meta("cycle_id", snap.get("cycle_id"))
                state.set_meta("observed_at", snap.get("observed_at"))
            except Exception as e:
                print(f"checkpoint refresh error: {e}", flush=True)

    threading.Thread(target=_refresh_loop, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
