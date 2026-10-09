"""Contract + unit tests for the Live Supervisor Dashboard backend slice.

These tests prove the honesty contract (§29) and the API contract:
  - every observed value carries a real source-state;
  - LIVE values degrade to STALE past the freshness window;
  - unreachable sources produce honest OFFLINE/UNKNOWN, never fabricated data;
  - the loopback API serves state/events/health with correct shapes;
  - the SSE framing matches node_server's so one client parser works;
  - the EventBus "*" subscription folds events into the ring;
  - git + ollama adapters report REAL state (LIVE_VERIFIED) for this repo/runtime.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from events import EventBus
from nodes import supervisor as sup


# --- SourceFact honesty -----------------------------------------------------
class TestSourceFactHonesty:
    def test_fresh_live_stays_live(self):
        f = sup.fact(42, sup.LIVE_VERIFIED, "git")
        assert f.effective_state() == sup.LIVE_VERIFIED

    def test_aged_live_degrades_to_stale(self):
        f = sup.SourceFact(42, sup.LIVE, "git", observed_at=time.time() - 999)
        assert f.effective_state() == sup.STALE

    def test_offline_never_upgraded_by_time(self):
        f = sup.SourceFact(None, sup.OFFLINE, "git", observed_at=time.time() - 999)
        assert f.effective_state() == sup.OFFLINE

    def test_unknown_state_rejected(self):
        with pytest.raises(ValueError):
            sup.fact(1, "MADE_UP_STATE", "x")

    def test_to_dict_carries_source_and_age(self):
        f = sup.fact("abc", sup.LIVE_VERIFIED, "git", note="head")
        d = f.to_dict()
        assert d["value"] == "abc"
        assert d["state"] == sup.LIVE_VERIFIED
        assert d["source"] == "git"
        assert "age_s" in d and "observed_at" in d
        assert d["note"] == "head"

    def test_not_exposed_is_honest_placeholder(self):
        f = sup.not_exposed("avatar render")
        assert f.effective_state() == sup.NOT_EXPOSED
        assert f.value is None


# --- git adapter ------------------------------------------------------------
class TestGitAdapter:
    def test_real_repo_reports_live_verified(self, tmp_path):
        # Use THIS repo (the worktree) — a real git repo, real state.
        import os
        repo = os.path.dirname(os.path.dirname(os.path.abspath(sup.__file__)))
        facts = sup.read_git_state(repo)
        assert "head" in facts
        assert facts["head"].effective_state() == sup.LIVE_VERIFIED
        assert isinstance(facts["head"].value, str) and facts["head"].value
        assert "branch" in facts
        assert "dirty_count" in facts

    def test_non_repo_reports_offline_not_fabricated(self):
        facts = sup.read_git_state("C:/does/not/exist/nope")
        # Honest OFFLINE with a reason; the only value is the path we were asked
        # about — never a fabricated head/branch/ahead-behind.
        assert facts["repo"].effective_state() == sup.OFFLINE
        assert "head" not in facts
        assert "branch" not in facts
        assert "ahead" not in facts


# --- ollama adapter ---------------------------------------------------------
class TestOllamaAdapter:
    def test_reports_structured_state_either_way(self):
        # Dead port -> honest OFFLINE with no fabricated version.
        dead = sup.read_ollama_state(base_url="http://127.0.0.1:1", timeout=1.5)
        assert "ollama" in dead
        assert dead["ollama"].effective_state() == sup.OFFLINE
        assert dead["ollama"].value is None

        # Real runtime (if up) -> LIVE_VERIFIED version; if down, OFFLINE.
        # Either way the shape is real, never a made-up version string.
        live = sup.read_ollama_state(timeout=2.0)
        if "version" in live:
            assert live["version"].effective_state() in (sup.LIVE_VERIFIED, sup.STALE)
            assert isinstance(live["version"].value, str) and live["version"].value
        else:
            assert live["ollama"].effective_state() == sup.OFFLINE


# --- normaliser + EventBus --------------------------------------------------
class TestNormaliser:
    def test_subscribes_to_bus_and_folds_events(self):
        bus = EventBus()
        st = sup.SupervisorState(bus=bus)
        bus.emit("execution.started", {"task": "t1"})
        bus.emit("execution.completed", {"task": "t1"})
        assert st.last_seq == 2
        evs = st.events_since(0)
        assert len(evs) == 2
        assert evs[0]["seq"] == 1 and evs[1]["seq"] == 2

    def test_events_since_cursor(self):
        bus = EventBus()
        st = sup.SupervisorState(bus=bus)
        for i in range(5):
            bus.emit("task.started", {"i": i})
        assert len(st.events_since(3)) == 2

    def test_event_ring_is_bounded(self):
        st = sup.SupervisorState(event_ring=3)
        for i in range(10):
            st.ingest({"name": f"e{i}"})
        assert st.last_seq == 10
        assert len(st.events_since(0)) == 3  # bounded to ring size
        assert st.events_since(0)[-1]["seq"] == 10

    def test_snapshot_shape(self):
        st = sup.SupervisorState()
        st.set_section("repositories", {"proj": {"head": sup.fact("abc", sup.LIVE_VERIFIED, "git").to_dict()}})
        snap = st.snapshot()
        assert snap["schema_version"] == sup.SCHEMA_VERSION
        assert "generated_at" in snap
        assert "repositories" in snap["sections"]
        # JSON-serialisable (the API relies on this)
        json.dumps(snap)


# --- loopback API -----------------------------------------------------------
class TestSupervisorAPI:
    @pytest.fixture()
    def server(self):
        st = sup.SupervisorState()
        st.set_section("repositories", {"p": {"head": sup.fact("deadbeef", sup.LIVE_VERIFIED, "git").to_dict()}})
        st.ingest({"name": "execution.started", "task": "t"})
        srv = sup.build_supervisor_server(st, host="127.0.0.1", port=0)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        port = srv.server_address[1]
        yield f"http://127.0.0.1:{port}", st
        srv.shutdown()
        srv.server_close()

    def test_health(self, server):
        base, _ = server
        with urllib.request.urlopen(base + "/v1/supervisor/health", timeout=5) as r:
            d = json.loads(r.read())
        assert d["ok"] is True
        assert d["schema_version"] == sup.SCHEMA_VERSION
        assert d["last_event_seq"] == 1

    def test_state_snapshot(self, server):
        base, _ = server
        with urllib.request.urlopen(base + "/v1/supervisor/state", timeout=5) as r:
            d = json.loads(r.read())
        assert d["ok"] is True
        assert d["snapshot"]["sections"]["repositories"]["p"]["head"]["value"] == "deadbeef"
        assert d["snapshot"]["sections"]["repositories"]["p"]["head"]["state"] == sup.LIVE_VERIFIED

    def test_events_sse_framing(self, server):
        base, _ = server
        with urllib.request.urlopen(base + "/v1/supervisor/events", timeout=5) as r:
            assert r.headers.get("Content-Type") == "text/event-stream"
            body = r.read().decode()
        # node_server-compatible framing: id:/event:/data: lines
        assert "id: " in body
        assert "event: supervisor" in body
        assert "data: " in body
        assert "execution.started" in body

    def test_events_since_cursor_over_http(self, server):
        base, _ = server
        with urllib.request.urlopen(base + "/v1/supervisor/events?since=1", timeout=5) as r:
            body = r.read().decode()
        # event seq 1 is excluded by the cursor -> empty stream
        assert "execution.started" not in body

    def test_unknown_route_404(self, server):
        base, _ = server
        try:
            urllib.request.urlopen(base + "/v1/supervisor/nope", timeout=5)
            assert False, "expected HTTPError"
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_public_bind_refused(self):
        st = sup.SupervisorState()
        with pytest.raises(ValueError):
            sup.build_supervisor_server(st, host="0.0.0.0")


# --- refresh wiring ---------------------------------------------------------
class TestRefresh:
    def test_refresh_populates_sections_with_real_states(self):
        import os
        repo = os.path.dirname(os.path.dirname(os.path.abspath(sup.__file__)))
        st = sup.SupervisorState()
        sup.refresh_snapshot(st, {"self": repo}, ollama_url="http://127.0.0.1:1")
        snap = st.snapshot()
        assert "repositories" in snap["sections"]
        assert snap["sections"]["repositories"]["self"]["head"]["state"] in (
            sup.LIVE_VERIFIED, sup.LIVE)
        # ollama pointed at a dead port -> honest OFFLINE, not a fake version
        assert snap["sections"]["local_models"]["ollama"]["state"] == sup.OFFLINE
        # no team registry wired -> honest NOT_EXPOSED, not a fabricated roster
        assert snap["sections"]["workers"]["note"]["state"] == sup.NOT_EXPOSED


# --- team registry adapter --------------------------------------------------
class TestTeamRegistryAdapter:
    def _make_registry(self):
        from compute.team_registry import TeamRegistry, WorkerCareerRecord
        reg = TeamRegistry()
        reg.register_worker(WorkerCareerRecord(
            worker_id="w-hermes", role_id="supervisor", department="orchestration",
            model_id=None, provider_id=None, execution_target="hermes-host",
            career_state="ACTIVE"))
        reg.register_worker(WorkerCareerRecord(
            worker_id="w-opencode", role_id="implementer", department="engineering",
            model_id="claude", provider_id="anthropic", execution_target="opencode-cli",
            career_state="ACTIVE"))
        return reg

    def test_list_workers_and_teams_exist(self):
        reg = self._make_registry()
        assert len(reg.list_workers()) == 2
        assert reg.list_teams() == []

    def test_adapter_reports_real_counts_live_verified(self):
        reg = self._make_registry()
        facts = sup.read_team_registry(reg)
        assert facts["worker_count"].effective_state() == sup.LIVE_VERIFIED
        assert facts["worker_count"].value == 2
        rows = facts["workers"].value
        ids = {r["worker_id"] for r in rows}
        assert ids == {"w-hermes", "w-opencode"}
        oc = next(r for r in rows if r["worker_id"] == "w-opencode")
        assert oc["execution_target"] == "opencode-cli"
        assert oc["career_state"] == "ACTIVE"

    def test_empty_registry_is_honest_not_fabricated(self):
        from compute.team_registry import TeamRegistry
        facts = sup.read_team_registry(TeamRegistry())
        assert facts["worker_count"].value == 0
        assert facts["workers"].value == []
        assert facts["worker_count"].effective_state() == sup.LIVE_VERIFIED

    def test_refresh_with_registry_populates_section(self):
        import os
        repo = os.path.dirname(os.path.dirname(os.path.abspath(sup.__file__)))
        reg = self._make_registry()
        st = sup.SupervisorState()
        sup.refresh_snapshot(st, {"self": repo}, ollama_url="http://127.0.0.1:1",
                             team_registry=reg)
        snap = st.snapshot()
        assert "team_registry" in snap["sections"]
        assert snap["sections"]["team_registry"]["worker_count"]["value"] == 2
        assert snap["sections"]["team_registry"]["worker_count"]["state"] == sup.LIVE_VERIFIED
        # the honest NOT_EXPOSED gap is closed once a registry is wired
        assert "workers" not in snap["sections"]


# --- OpenCode CLI adapter ---------------------------------------------------
class TestOpenCodeAdapter:
    def test_missing_binary_is_honest_offline(self):
        facts = sup.read_opencode_sessions(opencode_bin="definitely-not-opencode-xyz")
        # Under shell=True the shell returns a non-zero exit (DEGRADED) rather
        # than raising FileNotFoundError (OFFLINE). Both are honest; the
        # guarantee is "not LIVE and no fabricated data".
        assert facts["opencode"].effective_state() in (sup.OFFLINE, sup.DEGRADED)
        assert facts["opencode"].value is None

    def test_session_without_id_is_unknown(self):
        facts = sup.read_opencode_session(session_id="")
        assert facts["opencode_session"].effective_state() == sup.UNKNOWN

    def test_real_cli_reports_available(self):
        # opencode is verified on PATH in this environment.
        facts = sup.read_opencode_sessions()
        st = facts["cli"].effective_state()
        assert st in (sup.LIVE_VERIFIED, sup.STALE)
        assert facts["cli"].value == "available"
        assert facts["raw_line_count"].value >= 0

    def test_real_export_of_known_session(self):
        # The verified P0-A session id from reconciliation §10.
        facts = sup.read_opencode_session(
            session_id="ses_edf2e381fffetxJ8P6XCdR8Q35")
        if "session" in facts:
            s = facts["session"]
            assert s.effective_state() in (sup.LIVE_VERIFIED, sup.STALE)
            assert s.value.get("id") == "ses_edf2e381fffetxJ8P6XCdR8Q35"
            assert facts["message_count"].value >= 1
        else:
            # session may have aged out; must still be an honest state, not a crash
            assert facts["opencode_session"].effective_state() in (
                sup.OFFLINE, sup.DEGRADED, sup.UNKNOWN)

    def test_refresh_includes_opencode_section(self):
        import os
        repo = os.path.dirname(os.path.dirname(os.path.abspath(sup.__file__)))
        st = sup.SupervisorState()
        sup.refresh_snapshot(st, {"self": repo}, ollama_url="http://127.0.0.1:1",
                             opencode_bin="opencode")
        snap = st.snapshot()
        assert "opencode" in snap["sections"]
        assert snap["sections"]["opencode"]["cli"]["state"] in (
            sup.LIVE_VERIFIED, sup.STALE, sup.OFFLINE, sup.DEGRADED)
