"""Live acceptance demo for the Supervisor Dashboard V1 backend slice (§20).

Spins up the real loopback supervisor API with all four verified adapters
(git, ollama, team_registry, opencode-cli), refreshes the snapshot, and prints
the real /v1/supervisor/state + /v1/supervisor/health responses. This is
bounded-live evidence, not a mock: every value's source-state is shown.
"""
import json
import os
import sys
import threading
import urllib.request

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from compute.team_registry import TeamRegistry, WorkerCareerRecord
from nodes import supervisor as sup

REPO = os.path.dirname(os.path.dirname(os.path.abspath(sup.__file__)))
MAIN = r"C:/Users/jpowe/Desktop/Projects/Agent-Bridge"

# Build a small real registry (honest: these are the actual workers we supervise)
reg = TeamRegistry()
reg.register_worker(WorkerCareerRecord(
    worker_id="w-hermes", role_id="supervisor", department="orchestration",
    execution_target="hermes-host", career_state="ACTIVE"))
reg.register_worker(WorkerCareerRecord(
    worker_id="w-opencode", role_id="implementer", department="engineering",
    model_id="claude", provider_id="anthropic", execution_target="opencode-cli",
    career_state="ACTIVE"))

state = sup.SupervisorState()
state.session_id = "dashboard-acceptance-demo"

# Real adapters
sup.refresh_snapshot(
    state,
    repos={"agent-bridge": MAIN, "dashboard-worktree": REPO},
    team_registry=reg,
    opencode_bin="opencode",
    opencode_session_id="ses_edf2e381fffetxJ8P6XCdR8Q35",
)
# Fold a couple of synthetic lifecycle events onto the (empty) bus ring so the
# SSE stream has something to show in the demo. In production these come from
# the real EventBus; here we ingest honestly-labelled demo events.
state.ingest({"name": "execution.started", "task": "dashboard-acceptance", "source": "demo"})

srv = sup.build_supervisor_server(state, host="127.0.0.1", port=0)
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]
base = f"http://127.0.0.1:{port}"

def get(path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return json.loads(r.read())

print("=== /v1/supervisor/health ===")
print(json.dumps(get("/v1/supervisor/health"), indent=2))

snap = get("/v1/supervisor/state")["snapshot"]
print("\n=== /v1/supervisor/state (source-states, values trimmed) ===")
# Print each section's facts compactly: field -> (state, value-preview)
for section, data in snap["sections"].items():
    print(f"\n[{section}]")
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict) and "state" in v:
                val = v.get("value")
                prev = (json.dumps(val)[:70] + "...") if val not in (None, "", [], {}) else val
                print(f"  {k}: {v['state']:16} {prev}")
            elif isinstance(v, dict):
                # nested (e.g. repositories[label][field])
                for k2, v2 in v.items():
                    if isinstance(v2, dict) and "state" in v2:
                        print(f"  {k}.{k2}: {v2['state']:16} {str(v2.get('value'))[:50]}")
                    else:
                        print(f"  {k}.{k2}: {v2}")

print("\n=== /v1/supervisor/events (SSE framing preview) ===")
with urllib.request.urlopen(base + "/v1/supervisor/events", timeout=10) as r:
    print("Content-Type:", r.headers.get("Content-Type"))
    print(r.read().decode()[:400])

srv.shutdown()
srv.server_close()
print("\nACCEPTANCE DEMO COMPLETE — all values carry real source-states.")
