#!/usr/bin/env python
"""§16-§19: LIVE Supervisor Dashboard server.

Serves the real supervisor read-model (nodes/supervisor.py) on the loopback
port the IDE-Workspace UI proxies to (8472). Bound to the LIVE
SupervisorRuntime registry — the worker cards, quota states (Codex
WAITING_FOR_QUOTA), handoffs and events are the runtime's own, not synthetic
(§20.K: no fixture masquerading as live).

Usage:
    python scripts/serve_supervisor_dashboard.py [--port 8472]

The runtime daemon keeps checkpointing supervisor_state/; this server reads
that same state through the Supervisor registry so the UI and the daemon
never diverge.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from compute.supervisor_runtime import (  # noqa: E402
    CodexAdapter, OllamaAdapter, OpenCodeAdapter, SupervisorRuntime)
from nodes import supervisor as sup  # noqa: E402

REPOS = {
    "agent-bridge": "C:/Users/jpowe/Desktop/Projects/Agent-Bridge",
    "dashboard": "C:/Users/jpowe/Desktop/Projects/Agent-Bridge-dashboard",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8472)
    ap.add_argument("--state-dir", default="supervisor_state")
    ap.add_argument("--interval", type=float, default=120.0)
    args = ap.parse_args()

    # the LIVE runtime's registry is the single source of truth; the API is a
    # read-model over it (bus=None -> isolated state we feed via refresh).
    # Registered WITH the real adapters so worker cards/quota are live.
    runtime = SupervisorRuntime(
        args.state_dir, adapters=[OpenCodeAdapter(), CodexAdapter(),
                                  OllamaAdapter()],
        cycle_interval_s=args.interval)
    runtime.run_cycle()   # one live observation so the first page load is real
    state = sup.create_supervisor_state(session_id="dashboard")

    def _refresh() -> None:
        # supervisor= feeds the live registry in through the documented hook
        sup.refresh_snapshot(state, repos=REPOS,
                             supervisor=runtime.supervisor,
                             resource_governor=getattr(runtime,
                                                       "governor", None))

    _refresh()
    srv = sup.build_supervisor_server(state, host="127.0.0.1", port=args.port,
                                      runtime=runtime)
    print(f"Supervisor Dashboard API on http://127.0.0.1:{args.port} "
          f"(/v1/supervisor/health, /v1/supervisor/state)", flush=True)

    def _refresh_loop() -> None:
        while True:
            time.sleep(args.interval)
            try:
                runtime.run_cycle()
                _refresh()
            except Exception as e:  # noqa: BLE001 — never crash the server
                print(f"refresh error: {e}", flush=True)

    threading.Thread(target=_refresh_loop, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
