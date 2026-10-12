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

    def test_create_supervisor_state_factory_binds_bus(self):
        bus = EventBus()
        st = sup.create_supervisor_state(bus=bus, session_id="sess-1")
        assert st.session_id == "sess-1"
        bus.emit("task.started", {"task_id": "t1"})
        assert st.last_seq == 1
        # EventBus.emit passes {"event": <name>, "timestamp": ..., **payload}
        rec = st.events_since(0)[0]
        assert rec["event"]["event"] == "task.started"
        assert rec["event"]["task_id"] == "t1"

    def test_create_supervisor_state_without_bus_is_isolated(self):
        st = sup.create_supervisor_state()
        st.ingest({"name": "execution.started"})
        assert st.last_seq == 1
        assert st.session_id == ""


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


# --- §17.J / §18 control surface (worker detail + continue) -------------------
class _FakeAdapter:
    worker_id = "fake-1"
    application = "fakeapp"
    role = "tester"

    def status(self):
        return {"verdict": "IDLE", "evidence": ["fixture adapter"]}

    def current_task(self):
        return {"task": "bounded task", "evidence": []}

    def send_instruction(self, instruction, continue_task=False):
        return {"delivered": True, "channel": "fake", "evidence": ["ok"]}


class _FakeRuntime:
    """Stands in for SupervisorRuntime for the API route tests — the routes
    only call worker_detail()/control_continue(), so a minimal fake proves
    routing + wiring without touching real workers."""
    def __init__(self):
        self.adapters = {"fake-1": _FakeAdapter()}
        self.continued = []

    def worker_detail(self, worker_id):
        if worker_id not in self.adapters:
            return {"ok": False, "error_code": "UNKNOWN_WORKER"}
        a = self.adapters[worker_id]
        st = a.status()
        return {"ok": True, "worker_id": worker_id,
                "application": a.application, "role": a.role,
                "verdict": st["verdict"], "evidence": st["evidence"]}

    def control_continue(self, worker_id):
        if worker_id not in self.adapters:
            return {"ok": False, "error_code": "UNKNOWN_WORKER"}
        self.continued.append(worker_id)
        return {"ok": True, "worker_id": worker_id, "delivered": True,
                "channel": "fake", "evidence": ["ok"]}


class TestControlSurfaceRoutes:
    @pytest.fixture()
    def server(self):
        st = sup.SupervisorState()
        rt = _FakeRuntime()
        srv = sup.build_supervisor_server(st, host="127.0.0.1", port=0,
                                          runtime=rt)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        port = srv.server_address[1]
        yield f"http://127.0.0.1:{port}", rt
        srv.shutdown()
        srv.server_close()

    def test_worker_detail_get(self, server):
        base, _ = server
        with urllib.request.urlopen(base + "/v1/supervisor/worker/fake-1",
                                    timeout=5) as r:
            d = json.loads(r.read())
        assert d["ok"] is True
        assert d["worker_id"] == "fake-1"
        assert d["application"] == "fakeapp"
        assert d["verdict"] == "IDLE"

    def test_worker_detail_unknown_worker(self, server):
        base, _ = server
        with urllib.request.urlopen(base + "/v1/supervisor/worker/nope",
                                    timeout=5) as r:
            d = json.loads(r.read())
        assert d["ok"] is False
        assert d["error_code"] == "UNKNOWN_WORKER"

    def test_continue_post_uses_real_channel(self, server):
        base, rt = server
        req = urllib.request.Request(
            base + "/v1/supervisor/worker/fake-1/continue", data=b"{}",
            method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read())
        assert d["ok"] is True
        assert d["delivered"] is True
        assert rt.continued == ["fake-1"]     # the runtime actually acted

    def test_worker_detail_503_without_runtime(self):
        st = sup.SupervisorState()
        srv = sup.build_supervisor_server(st, host="127.0.0.1", port=0)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            urllib.request.urlopen(base + "/v1/supervisor/worker/fake-1",
                                   timeout=5)
            assert False, "expected HTTPError"
        except urllib.error.HTTPError as e:
            assert e.code == 503
        finally:
            srv.shutdown()
            srv.server_close()


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


class TestOpenCodeLiveness:
    def test_missing_binary_is_honest_offline(self):
        # No CLI and (in the test host) the tasklist signal may still find a
        # process; the guarantee is the verdict is a real derived state, never
        # a fabricated ACTIVE, and cli is honestly OFFLINE.
        facts = sup.read_opencode_liveness(opencode_bin="definitely-not-opencode-xyz")
        assert facts["cli"].effective_state() == sup.OFFLINE
        assert facts["verdict"].value in ("ACTIVE", "IDLE", "OFFLINE")
        assert facts["verdict"].effective_state() in (sup.LIVE_VERIFIED, sup.OFFLINE)

    def test_real_liveness_verdict(self):
        facts = sup.read_opencode_liveness()
        assert facts["process_present"].effective_state() in (
            sup.LIVE_VERIFIED, sup.OFFLINE)
        # freshest_session only present when the db channel answered.
        if "freshest_session" in facts:
            fs = facts["freshest_session"]
            assert fs.effective_state() in (sup.LIVE_VERIFIED, sup.STALE)
            assert isinstance(fs.value, dict) and "time_updated" in fs.value
        assert facts["verdict"].value in ("ACTIVE", "IDLE", "OFFLINE")


class TestCodexAdapter:
    def test_missing_home_is_honest_offline(self, tmp_path):
        # A codex home with no sessions/ dir must report OFFLINE, never invent
        # sessions.
        facts = sup.read_codex_state(codex_home=str(tmp_path / "nope"))
        assert facts["codex"].effective_state() == sup.OFFLINE
        assert facts["codex"].value is None
        assert facts["cli"].effective_state() in (sup.LIVE_VERIFIED, sup.OFFLINE)

    def test_empty_sessions_dir_is_offline(self, tmp_path):
        home = tmp_path / ".codex"
        (home / "sessions" / "2026" / "10" / "12").mkdir(parents=True)
        facts = sup.read_codex_state(codex_home=str(home))
        assert facts["codex"].effective_state() == sup.OFFLINE
        assert facts["codex"].value is None

    def test_fake_rollout_parses_first_and_last(self, tmp_path):
        home = tmp_path / ".codex"
        day = home / "sessions" / "2026" / "10" / "12"
        day.mkdir(parents=True)
        rollout = day / "rollout-2026-10-12T10-00-00-aaaa-bbbb.jsonl"
        import json as _json
        lines = [
            {"timestamp": "2026-10-12T10:00:00.000Z", "type": "session_meta",
             "payload": {"id": "aaaa-bbbb", "cwd": "/tmp/proj",
                         "originator": "codex_work_desktop"}},
            {"timestamp": "2026-10-12T10:05:00.000Z", "type": "event_msg",
             "payload": {}},
        ]
        rollout.write_text("\n".join(_json.dumps(x) for x in lines), encoding="utf-8")
        facts = sup.read_codex_state(codex_home=str(home),
                                     heartbeat_active_s=999999.0)
        assert facts["rollout_count"].value == 1
        sess = facts["sessions"].value
        assert len(sess) == 1
        assert sess[0]["id"] == "aaaa-bbbb"
        assert sess[0]["cwd"] == "/tmp/proj"
        assert sess[0]["last_event_at"] == "2026-10-12T10:05:00.000Z"
        assert facts["verdict"].value == "ACTIVE"

    def test_no_secret_fields_in_output(self, tmp_path):
        # The adapter must never surface auth/token/credential material.
        home = tmp_path / ".codex"
        day = home / "sessions" / "2026" / "10" / "12"
        day.mkdir(parents=True)
        # plant decoy secret files the adapter must NOT read
        (home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-SECRET"}',
                                        encoding="utf-8")
        (home / ".sandbox-secrets").mkdir()
        (home / ".sandbox-secrets" / "s.txt").write_text("SECRET", encoding="utf-8")
        rollout = day / "rollout-2026-10-12T10-00-00-aaaa-bbbb.jsonl"
        import json as _json
        rollout.write_text(_json.dumps(
            {"timestamp": "2026-10-12T10:00:00.000Z", "type": "session_meta",
             "payload": {"id": "aaaa-bbbb"}}), encoding="utf-8")
        facts = sup.read_codex_state(codex_home=str(home))
        blob = _json.dumps({k: v.to_dict() for k, v in facts.items()})
        assert "SECRET" not in blob
        assert "sk-" not in blob


class TestRefreshExternalWorkers:
    def test_refresh_populates_codex_and_liveness(self, tmp_path):
        import os
        repo = os.path.dirname(os.path.dirname(os.path.abspath(sup.__file__)))
        home = tmp_path / ".codex"
        day = home / "sessions" / "2026" / "10" / "12"
        day.mkdir(parents=True)
        import json as _json
        (day / "rollout-2026-10-12T10-00-00-aaaa-bbbb.jsonl").write_text(
            _json.dumps({"timestamp": "2026-10-12T10:00:00.000Z",
                         "type": "session_meta", "payload": {"id": "aaaa-bbbb"}}),
            encoding="utf-8")
        st = sup.SupervisorState()
        sup.refresh_snapshot(st, {"self": repo}, ollama_url="http://127.0.0.1:1",
                             opencode_bin="opencode", codex_home=str(home))
        snap = st.snapshot()
        assert "codex" in snap["sections"]
        assert snap["sections"]["codex"]["verdict"]["value"] in (
            "ACTIVE", "IDLE", "UNKNOWN")
        assert "liveness" in snap["sections"]["opencode"]

    def test_heartbeat_emits_only_on_change(self):
        st = sup.SupervisorState()
        # first sight always emits
        sup._emit_verdict_change(st, "codex", "ACTIVE")
        assert st.last_seq >= 1
        # same verdict -> no new event (coalescing)
        seq = st.last_seq
        sup._emit_verdict_change(st, "codex", "ACTIVE")
        assert st.last_seq == seq
        # change -> emits again
        sup._emit_verdict_change(st, "codex", "IDLE")
        assert st.last_seq > seq


class TestHiveDashboardSection:
    def test_hive_not_wired_is_not_exposed(self):
        st = sup.SupervisorState()
        facts = sup.read_hive_state(None)
        assert facts["hive"].effective_state() == sup.NOT_EXPOSED

    def test_hive_section_populated_from_live_scheduler(self):
        from compute.hive_scheduler import (
            FREE_TIER, LOCAL_UNLIMITED, QuotaLedgerEntry, HiveScheduler,
            TaskSpec)
        h = HiveScheduler()
        h.register_worker("w-local", provider="ollama",
                          tier=LOCAL_UNLIMITED, capabilities=("CODING_AGENT",))
        h.register_worker("w-cloud", provider="freecloud",
                          tier=FREE_TIER, capabilities=("RESEARCH",))
        h.record_quota(QuotaLedgerEntry(
            worker_id="w-cloud", provider="freecloud", tier=FREE_TIER,
            quota_total=100.0, quota_remaining=40.0, confidence="VERIFIED"))
        h.route(TaskSpec(task_id="t1", title="t1",
                         required_capability="CODING_AGENT"))
        st = sup.SupervisorState()
        sup.refresh_snapshot(st, {}, ollama_url="http://127.0.0.1:1", hive=h)
        snap = st.snapshot()
        assert "hive" in snap["sections"]
        hive_sec = snap["sections"]["hive"]
        assert hive_sec["overview"]["state"] in (sup.LIVE_VERIFIED, sup.STALE)
        ov = hive_sec["overview"]["value"]
        assert ov["workers"] == 2
        assert ov["tasks_assigned"] == 1
        # §38 honesty: the known quota shows its fraction; UNKNOWN would be None
        quotas = hive_sec["quotas"]["value"]
        assert quotas[0]["remaining_fraction"] == 0.4

    # --- §35 supervision + resources + knowledge dashboard sections -----------
    def test_supervision_section_populated(self):
        from compute.supervision import Gap, Handoff, Supervisor
        sv = Supervisor()
        sv.register_worker("w-1", "EXTERNAL_AI_AGENT", "opencode",
                           role="ide-worker")
        sv.submit_handoff(Handoff(task_id="t-1", worker_id="w-1",
                                  project="agent-bridge"))
        sv.record_gap(Gap(gap_id="g-1", severity="HIGH", category="test",
                          description="missing coverage"))
        st = sup.SupervisorState()
        sup.refresh_snapshot(st, {}, ollama_url="http://127.0.0.1:1",
                             supervisor=sv)
        sec = st.snapshot()["sections"]["supervision"]
        assert sec["workers_total"]["value"] == 1
        assert sec["handoffs_pending"]["value"] == 1
        assert sec["gaps_open"]["value"] == 1
        # §2 completion directive: continuation_required is an honest flag
        assert sec["continuation_required"]["value"] is True
        assert sec["workers_by_status"]["value"]["AWAITING_QA"] == 1

    def test_supervision_error_is_degraded_not_fatal(self):
        class Broken:
            def overview(self):
                raise RuntimeError("boom")
        st = sup.SupervisorState()
        sup.refresh_snapshot(st, {}, ollama_url="http://127.0.0.1:1",
                             supervisor=Broken())
        sec = st.snapshot()["sections"]["supervision"]
        assert sec["error"]["state"] == sup.DEGRADED

    def test_resources_section_populated(self):
        from compute.resource_governor import ResourceGovernor, ResourceSample
        g = ResourceGovernor()
        g._sample = ResourceSample(cpu=0.4, ram=0.7, confidence="VERIFIED")
        st = sup.SupervisorState()
        sup.refresh_snapshot(st, {}, ollama_url="http://127.0.0.1:1",
                             resource_governor=g)
        sec = st.snapshot()["sections"]["resources"]
        assert sec["pressure_state"]["value"] in (
            "HEALTHY", "ELEVATED", "PRESSURE", "CRITICAL")
        assert sec["sample"]["value"]["cpu"] == 0.4

    def test_knowledge_section_populated(self):
        from compute.knowledge_index import KnowledgeIndex, KnowledgeObject
        idx = KnowledgeIndex()
        idx._objects = {
            "h1": KnowledgeObject(object_id="h1", source_id="chat_exports",
                                  source_type="CHAT_EXPORT", path="/x/a.txt",
                                  project="genesis", confidence="VERIFIED"),
            "h2": KnowledgeObject(object_id="h2", source_id="master_prompts",
                                  source_type="PROMPT_ARCHIVE",
                                  path="/x/b.txt", project="unmapped",
                                  confidence="VERIFIED"),
        }
        st = sup.SupervisorState()
        sup.refresh_snapshot(st, {}, ollama_url="http://127.0.0.1:1",
                             knowledge_index=idx)
        sec = st.snapshot()["sections"]["knowledge"]
        assert sec["objects"]["value"] == 2
        assert sec["by_project"]["value"]["genesis"] == 1
