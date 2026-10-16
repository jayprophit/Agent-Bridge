/* Aetherius Supervisor Dashboard controller (v1.1).
 *
 * One session shared by Chat/Work/Team/Monitor; switching views never creates
 * a new session. Live read-only data comes from the supervisor API on the same
 * origin (/v1/supervisor/{health,state,events,worker/<id>}). Task submit tries
 * the Agent-Bridge session API and degrades to a local hold queue when the
 * bridge is unreachable (no silent drops, no fabricated success).
 *
 * Avatar: image-state renderer always on; optional 3D (three.js GLB) toggled
 * with #btn-3d, lazily imported. Both renderers sit on the same event bus and
 * replay lastAvatarState on switch, so state/emotion/visemes stay in sync.
 * TTS speech drives viseme lip-sync (3D jaw; bars animate for the image view).
 *
 * URL params: ?sup=<base> (default same-origin) ?bridge=<base> (default :8471)
 */
(function () {
  "use strict";

  var qp = new URLSearchParams(window.location.search);
  var SUP_BASE = qp.get("sup") || "";
  var BRIDGE_BASE = qp.get("bridge") || "http://127.0.0.1:8471";
  var PORTAL_BASE = qp.get("portal") || "http://127.0.0.1:9119";
  var PORTAL_PROFILE = qp.get("profile") || "aetherius-build";
  var STORE_SID = "aetherius.supervisor.sessionId";
  var sessionId = localStorage.getItem(STORE_SID) ||
    "sup-" + Math.random().toString(36).slice(2, 10);
  localStorage.setItem(STORE_SID, sessionId);

  var face = null;
  var threeApi = null;
  var threeLoading = false;
  var view3d = false;
  var lastSeq = 0;
  var lastBridgeSeq = 0;
  var supWasOnline = null;
  var bridgeOnline = false;
  var held = [];
  var activeAgent = null;

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var d = document.createElement(tag);
    if (cls) d.className = cls;
    if (text !== undefined) d.textContent = text;
    return d;
  }
  function short(s, n) {
    s = String(s == null ? "" : s);
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }
  function ts() { return new Date().toTimeString().slice(0, 8); }
  function fmtStamp(v) {
    if (v === undefined || v === null || v === "") return "";
    if (typeof v === "number") {
      var ms = v > 1e12 ? v : v * 1000;
      var d = new Date(ms);
      return isNaN(d) ? String(v) : d.toTimeString().slice(0, 8);
    }
    return String(v).slice(0, 19);
  }
  function unwrap(v) { return (v && typeof v === "object" && "value" in v) ? v.value : v; }
  function unwrapSection(sec) {
    sec = unwrap(sec);
    var out = {};
    if (sec && typeof sec === "object") {
      Object.keys(sec).forEach(function (k) { out[k] = unwrap(sec[k]); });
    }
    return out;
  }
  function asList(v) {
    v = unwrap(v);
    if (!v) return [];
    return Array.isArray(v) ? v : Object.keys(v).map(function (k) { return v[k]; });
  }
  function statusClass(s) {
    s = String(s || "").toUpperCase();
    if (/RUN|WORK|ACTIVE|EXEC|BUSY/.test(s)) return "run";
    if (/FAIL|ERROR|BLOCK|STUCK|ABORT/.test(s)) return "err";
    if (/WAIT|PEND|STALL|RETRY/.test(s)) return "warn";
    if (/IDLE|READY|OK|DONE|COMPLETE|LIVE/.test(s)) return "ok";
    return "";
  }
  function setBadge(id, cls, text) {
    var b = $(id);
    if (!b) return;
    b.className = "badge " + (cls || "");
    b.textContent = text;
  }

  function transcript(who, text, cls) {
    var t = $("transcript");
    if (!t) return null;
    var d = el("div", cls || "");
    d.appendChild(el("span", "who", who + ": "));
    d.appendChild(document.createTextNode(text));
    d.appendChild(el("span", "tstamp", ts()));
    t.appendChild(d);
    t.scrollTop = t.scrollHeight;
    return d;
  }
  function feedLine(text) {
    var f = $("feed");
    if (!f) return;
    f.appendChild(el("div", "feedline", ts() + " " + text));
    while (f.children.length > 200) f.removeChild(f.firstChild);
    f.scrollTop = f.scrollHeight;
  }

  /* ---- avatar: shared event bus for image + 3D renderers ---------------- */

  var lastAvatarState = { event: "IDLE", emotion: "neutral" };

  function syncLabel() {
    var label = $("avatar-state");
    if (!label) return;
    var txt = lastAvatarState.event + ((view3d && threeApi) ? " [3d]" : "");
    if (lastAvatarState.emotion && lastAvatarState.emotion !== "neutral") {
      txt += " · " + lastAvatarState.emotion;
    }
    if (label.textContent !== txt) label.textContent = txt;
  }

  function avatarEvent(ev) {
    if (ev.event) lastAvatarState.event = ev.event;
    if (ev.emotion) lastAvatarState.emotion = ev.emotion;
    if (ev.viseme !== undefined) lastAvatarState.viseme = ev.viseme;
    if (face) face.apply(ev);
    if (threeApi) threeApi.apply(ev);
    syncLabel();
  }
  function flash(state, ms) {
    avatarEvent({ event: state });
    setTimeout(function () { avatarEvent({ event: "IDLE" }); }, ms || 4000);
  }

  function show3d(on) {
    view3d = on;
    var wrap = $("face-wrap"), cv = $("avatar-canvas"), b = $("btn-3d");
    if (wrap) wrap.classList.toggle("hidden", on);
    if (cv) cv.classList.toggle("hidden", !on);
    if (b) b.classList.toggle("on", on);
    if (on && threeApi) threeApi.apply(lastAvatarState);
    else if (!on && face) face.apply(lastAvatarState);
    syncLabel();
  }

  function set3d(on) {
    if (on && !threeApi) {
      if (threeLoading) return;
      var cv = $("avatar-canvas");
      if (!cv) return;
      threeLoading = true;
      import("./avatar-three.js").then(function () {
        if (!window.AvatarThree) throw new Error("AvatarThree missing");
        return window.AvatarThree.createThreeRenderer(cv, "assets/reference-avatar.glb");
      }).then(function (api) {
        threeApi = api;
        threeLoading = false;
        show3d(true);
        feedLine("3D avatar online (" + (api.nodeNames || []).length + " nodes)");
      }).catch(function (e) {
        threeLoading = false;
        feedLine("3D avatar failed: " + (e && e.message) + " — staying on image states");
      });
      return;
    }
    show3d(on);
  }

  /* ---- supervisor read-only API ---------------------------------------- */

  function pollHealth() {
    fetch(SUP_BASE + "/v1/supervisor/health", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
      .then(function (h) {
        supWasOnline = true;
        setBadge("sup-badge", "ok", "SUP: live · seq " + (h.last_event_seq || 0));
      })
      .catch(function () {
        if (supWasOnline !== false) {
          supWasOnline = false;
          setBadge("sup-badge", "err", "SUP: offline");
          var rl = $("roster-list");
          if (rl) {
            rl.innerHTML = "";
            rl.appendChild(el("div", "empty",
              "Supervisor API offline. Start: python scripts/serve_supervisor_dashboard.py"));
          }
          feedLine("supervisor API unreachable");
        }
      });
  }

  function pollState() {
    fetch(SUP_BASE + "/v1/supervisor/state", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
      .then(function (s) { if (s && s.snapshot) applyState(s.snapshot); })
      .catch(function () {});
  }

  function applyState(snapshot) {
    var sections = snapshot.sections || {};
    var auth = unwrapSection(sections.authority);
    if (auth.stale) {
      setBadge("sup-badge", "warn", "SUP: stale " + Math.round(auth.observed_age_s || 0) + "s");
    } else if (supWasOnline !== false) {
      setBadge("sup-badge", "ok", "SUP: live · cycle " +
        (auth.cycle_id === undefined || auth.cycle_id === null ? "—" : auth.cycle_id));
    }
    var sup = unwrapSection(sections.supervision);
    var workers = asList(sup.workers);
    renderRoster(workers, auth);
    renderTeam(workers);
    renderMonitor(snapshot);
    var ap = $("approvals");
    if (ap) {
      var pending = sup.handoffs_pending;
      ap.textContent = "approvals: " + (pending ? pending : "none");
    }
  }

  function renderRoster(workers, auth) {
    var rl = $("roster-list");
    if (!rl) return;
    rl.innerHTML = "";
    var synth = {
      worker_id: "aetherius-supervisor",
      role: "supervisor",
      status: (auth && auth.stale) ? "STALE" : "LIVE",
      task_description: "read-only monitoring of all workers",
    };
    [synth].concat(workers).forEach(function (w) {
      var a = el("div", "agent");
      if (activeAgent === w.worker_id) a.classList.add("sel");
      a.appendChild(el("span", "dot " + statusClass(w.status)));
      var meta = el("div", "meta");
      meta.appendChild(el("div", "name", w.worker_id || w.name || "worker"));
      var line = [w.status, w.phase, w.role].filter(Boolean).join(" · ");
      if (line) meta.appendChild(el("div", "sub", line));
      var sub2 = w.task_description ? short(w.task_description, 64) : (w.project || "");
      if (sub2) meta.appendChild(el("div", "sub", sub2));
      a.appendChild(meta);
      if (w.worker_id === "aetherius-supervisor") {
        var pb = el("button", "", "portal");
        pb.title = "Hermes web portal (" + PORTAL_PROFILE + ")";
        pb.style.marginLeft = "auto";
        pb.style.alignSelf = "center";
        pb.onclick = function (e) {
          if (e && e.stopPropagation) e.stopPropagation();
          window.open(PORTAL_BASE + "/chat?profile=" + encodeURIComponent(PORTAL_PROFILE), "_blank");
        };
        a.appendChild(pb);
      }
      a.onclick = function () {
        activeAgent = w.worker_id;
        renderRoster(workers, auth);
        transcript("system", "selected agent: " + w.worker_id +
          (w.task_description ? " · " + short(w.task_description, 120) : ""), "sys");
      };
      rl.appendChild(a);
    });
    var cnt = $("roster-count");
    if (cnt) cnt.textContent = "(" + workers.length + ")";
  }

  function renderTeam(workers) {
    var g = $("team-grid");
    if (!g) return;
    if (!workers.length) {
      g.innerHTML = "";
      g.appendChild(el("div", "empty", "no workers in supervisor state"));
      return;
    }
    g.innerHTML = "";
    workers.forEach(function (w) {
      var card = el("div", "wcard");
      card.appendChild(el("h4", "", w.worker_id || "worker"));
      [["status", w.status], ["role", w.role], ["provider", w.provider],
       ["model", w.model], ["phase", w.phase],
       ["handoff", w.handoff_state], ["review", w.review_state],
       ["quota", w.quota_state],
       ["heartbeat", fmtStamp(w.last_heartbeat)],
       ["task", w.task_description]
      ].forEach(function (kv) {
        if (kv[1] === undefined || kv[1] === null || kv[1] === "") return;
        var row = el("div", "kv");
        row.appendChild(el("span", "", kv[0]));
        row.appendChild(el("span", "", short(String(kv[1]), 90)));
        card.appendChild(row);
      });
      var btn = el("button", "", "Continue");
      btn.onclick = function () { continueWorker(w.worker_id, btn); };
      card.appendChild(btn);
      g.appendChild(card);
    });
  }

  function continueWorker(id, btn) {
    btn.disabled = true;
    fetch(SUP_BASE + "/v1/supervisor/worker/" + encodeURIComponent(id) + "/continue",
          { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
      .then(function (r) { return r.json(); })
      .then(function (r) {
        feedLine("continue " + id + " -> " +
          (r && r.ok === false ? (r.error_code || "error") : "issued"));
      })
      .catch(function () { feedLine("continue " + id + " -> supervisor API unreachable"); })
      .then(function () { btn.disabled = false; });
  }

  function renderMonitor(snapshot) {
    var m = $("monitor");
    if (!m) return;
    m.innerHTML = "";
    var sections = snapshot.sections || {};
    var names = Object.keys(sections);
    if (!names.length) {
      m.appendChild(el("div", "empty", "no sections in snapshot"));
      return;
    }
    names.forEach(function (name) {
      var sec = unwrap(sections[name]);
      var det = el("details");
      det.appendChild(el("summary", "", name));
      if (sec && typeof sec === "object" && !Array.isArray(sec)) {
        var tbl = el("table", "mono");
        Object.keys(sec).forEach(function (k) {
          var v = sec[k];
          var state = "";
          if (v && typeof v === "object" && "value" in v) { state = v.state || ""; v = v.value; }
          if (v && typeof v === "object") v = JSON.stringify(v);
          var tr = el("tr");
          tr.appendChild(el("td", "", k));
          tr.appendChild(el("td", "", state));
          tr.appendChild(el("td", "", short(String(v), 160)));
          tbl.appendChild(tr);
        });
        det.appendChild(tbl);
      } else {
        det.appendChild(el("pre", "", short(String(sec), 2000)));
      }
      var raw = el("details");
      raw.appendChild(el("summary", "", "raw " + name));
      raw.appendChild(el("pre", "", short(JSON.stringify(sections[name], null, 1), 4000)));
      det.appendChild(raw);
      m.appendChild(det);
    });
  }

  function startEvents() {
    if (!window.EventSource) return;
    var es = new EventSource(SUP_BASE + "/v1/supervisor/events");
    es.addEventListener("supervisor", function (msg) {
      var e = null;
      try { e = JSON.parse(msg.data); } catch (err) { return; }
      if (e.seq && e.seq <= lastSeq) return;
      if (e.seq) lastSeq = e.seq;
      var parts = [e.event || "event"];
      if (e.worker) parts.push(e.worker);
      if (e.verdict) parts.push("· " + e.verdict);
      var extra = e.message || e.text || e.detail;
      if (extra) parts.push("· " + short(extra, 80));
      feedLine(parts.join(" "));
      var evName = String(e.event || "");
      var verdict = String(e.verdict || "");
      if (/blocked|fail|error|abort/i.test(evName) || /STALL|BLOCK|FAIL/i.test(verdict)) {
        flash("ERROR", 5000);
      } else if (/tool/i.test(evName)) {
        flash("WORKING", 6000);
        var tl = $("tools");
        if (tl) tl.textContent = "tools: " + short(e.tool || evName, 60);
      } else if (/heartbeat|started|progress/i.test(evName)) {
        avatarEvent({ event: "THINKING" });
      }
    });
  }

  /* ---- bridge task submit (degrade-safe) -------------------------------- */

  function pingBridge() {
    fetch(BRIDGE_BASE + "/v1/sessions", { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
      .then(function () {
        if (bridgeOnline === false) feedLine("bridge back online");
        bridgeOnline = true;
        setBadge("bridge-badge", "ok", "BRIDGE: live");
        flushHeld();
      })
      .catch(function () {
        if (bridgeOnline) feedLine("bridge unreachable");
        bridgeOnline = false;
        setBadge("bridge-badge", "warn", "BRIDGE: offline");
      });
  }

  function ensureSession() {
    return fetch(BRIDGE_BASE + "/v1/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: "supervisor-ui", mode: "", approval: "", interactive: true })
    }).then(function (r) { return r.json(); }).then(function (r) {
      var id = r && (r.session_id || r.id || r.sessionId || r.sid);
      if (id) {
        sessionId = id;
        localStorage.setItem(STORE_SID, id);
        showSession();
      }
      return id;
    });
  }

  function postTask(text) {
    var body = JSON.stringify({
      text: text,
      idempotency_key: "ui-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8),
      parent_task_id: ""
    });
    return fetch(BRIDGE_BASE + "/v1/sessions/" + encodeURIComponent(sessionId) + "/tasks",
          { method: "POST", headers: { "Content-Type": "application/json" }, body: body })
      .then(function (r) { return r.json().then(function (j) { return { status: r.status, j: j }; }); })
      .then(function (res) {
        if (res.status === 404) {
          return ensureSession().then(function (id) {
            if (!id) throw new Error("session create failed");
            return fetch(BRIDGE_BASE + "/v1/sessions/" + encodeURIComponent(id) + "/tasks",
                  { method: "POST", headers: { "Content-Type": "application/json" }, body: body })
              .then(function (r) { return r.json(); });
          });
        }
        if (res.status >= 400) {
          throw new Error("http " + res.status + ((res.j && res.j.error_code) ? " " + res.j.error_code : ""));
        }
        return res.j;
      });
  }

  function send(text) {
    if (!text) return;
    transcript("you", text);
    avatarEvent({ event: "THINKING" });
    if (!bridgeOnline) {
      held.push({ text: text, at: Date.now() });
      transcript("system", "bridge offline — message held locally (" + held.length + " queued)", "held");
      return;
    }
    postTask(text).then(function (r) {
      var tid = r && (r.task_id || r.task || r.id);
      transcript("system", "queued on bridge" + (tid ? " · task " + tid : ""));
    }).catch(function (err) {
      held.push({ text: text, at: Date.now() });
      transcript("system", "bridge send failed (" + (err && err.message) + ") — held locally (" + held.length + " queued)", "held");
    });
  }

  function flushHeld() {
    if (!held.length) return;
    var batch = held.splice(0, held.length);
    feedLine("flushing " + batch.length + " held message(s) to bridge");
    batch.forEach(function (m) {
      postTask(m.text).then(function (r) {
        var tid = r && (r.task_id || r.task || r.id);
        transcript("system", "held message delivered" + (tid ? " · task " + tid : ""));
      }).catch(function (err) {
        held.push(m);
        transcript("system", "held message still undeliverable (" + (err && err.message) + ")", "held");
      });
    });
  }

  function pollBridgeEvents() {
    if (!bridgeOnline) return;
    fetch(BRIDGE_BASE + "/v1/sessions/" + encodeURIComponent(sessionId) +
          "/events?since=" + lastBridgeSeq, { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
      .then(function (r) {
        var evs = (r && (r.events || r.items)) || [];
        evs.forEach(function (e) {
          if (e.seq && e.seq > lastBridgeSeq) lastBridgeSeq = e.seq;
          var type = String(e.type || e.event || "");
          var text = e.text || e.message || e.detail || "";
          if (!text) return;
          if (/message|assistant|reply|final|output/i.test(type)) {
            transcript("supervisor", short(String(text), 500));
            speak(String(text));
          }
        });
      })
      .catch(function () {});
  }

  /* ---- voice: STT push-to-talk + call mode, TTS + viseme lip-sync ------- */

  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var rec = null;
  var recActive = false;
  var callMode = false;
  var ttsOn = false;
  var VISEMES = ["aa", "E", "O", "nn", "DD", "kk", "I", "U", "RR", "TH"];
  var visIdx = 0;
  var visTimer = null;

  function startVisemes() {
    stopVisemes();
    visIdx = 0;
    visTimer = setInterval(function () {
      visIdx = (visIdx + 1) % VISEMES.length;
      avatarEvent({ viseme: VISEMES[visIdx], intensity: 0.45 + Math.random() * 0.25 });
    }, 110);
  }
  function stopVisemes() {
    if (visTimer) { clearInterval(visTimer); visTimer = null; }
    avatarEvent({ viseme: "sil" });
  }

  function updateVoiceLine() {
    var vl = $("voice-line");
    if (vl) {
      vl.textContent = "voice: mic " +
        (recActive ? "listening…" : (SR ? "ready" : "unavailable")) +
        " · tts " + (ttsOn ? "on" : "off") + (callMode ? " · call mode" : "");
    }
    var mic = $("btn-mic");
    if (mic) mic.classList.toggle("on", recActive);
  }

  function initVoice() {
    if (!SR) { updateVoiceLine(); return; }
    rec = new SR();
    rec.interimResults = true;
    rec.continuous = false;
    rec.lang = "en-GB";
    rec.onresult = function (e) {
      var interim = "", final = "";
      for (var i = e.resultIndex; i < e.results.length; i++) {
        var r = e.results[i];
        if (r.isFinal) final += r[0].transcript; else interim += r[0].transcript;
      }
      var input = $("text-input");
      if (interim && input) input.value = interim;
      if (final) {
        if (input) input.value = "";
        if (callMode) send(final.trim());
        else if (input) input.value = final.trim();
      }
    };
    rec.onstart = function () { recActive = true; avatarEvent({ event: "LISTENING" }); updateVoiceLine(); };
    rec.onend = function () {
      recActive = false;
      updateVoiceLine();
      if (callMode) setTimeout(function () { try { rec.start(); } catch (e) {} }, 250);
      else avatarEvent({ event: "IDLE" });
    };
    rec.onerror = function (ev) {
      if (ev && (ev.error === "not-allowed" || ev.error === "service-not-allowed")) {
        feedLine("microphone permission denied — voice input disabled");
        callMode = false;
        var b = $("btn-call");
        if (b) b.classList.remove("on");
        updateVoiceLine();
      }
    };
    updateVoiceLine();
  }

  function startPtt() {
    if (!rec || recActive) return;
    try { rec.continuous = callMode; rec.start(); } catch (e) {}
  }
  function stopPtt() {
    if (!rec || !recActive || callMode) return;
    try { rec.stop(); } catch (e) {}
  }
  function toggleCall() {
    callMode = !callMode;
    var b = $("btn-call");
    if (b) b.classList.toggle("on", callMode);
    if (callMode) {
      setTts(true);
      startPtt();
      feedLine("call mode on — continuous listening");
    } else {
      if (rec) { try { rec.stop(); } catch (e) {} }
      feedLine("call mode off");
    }
    updateVoiceLine();
  }
  function setTts(on) {
    ttsOn = on;
    var b = $("btn-tts");
    if (b) {
      b.textContent = "TTS " + (on ? "on" : "off");
      b.classList.toggle("on", on);
    }
    updateVoiceLine();
  }
  function speak(text) {
    if (!ttsOn || !window.speechSynthesis) return;
    try {
      var u = new SpeechSynthesisUtterance(text);
      u.rate = 1.02;
      var vs = window.speechSynthesis.getVoices() || [];
      var v = vs.filter(function (x) { return /en[-_]?GB/i.test(x.lang || ""); })[0] ||
              vs.filter(function (x) { return /^en/i.test(x.lang || ""); })[0];
      if (v) u.voice = v;
      u.onstart = function () { avatarEvent({ event: "SPEAKING" }); startVisemes(); };
      u.onend = function () { stopVisemes(); avatarEvent({ event: "IDLE" }); };
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    } catch (e) {}
  }

  /* ---- shell: views, dock, session -------------------------------------- */

  function showSession() {
    var b = $("session-id");
    if (b) b.textContent = sessionId;
  }
  function setView(name) {
    document.body.setAttribute("data-view", name);
    ["chat", "work", "team", "monitor"].forEach(function (v) {
      var s = $(v + "view");
      if (s) s.classList.toggle("hidden", v !== name);
    });
    Array.prototype.forEach.call(document.querySelectorAll("#viewbar button"), function (b) {
      b.classList.toggle("on", b.getAttribute("data-view") === name);
    });
    showSession();
  }
  function setDock(side) {
    document.body.setAttribute("data-dock", side);
    document.body.classList.toggle("dock-left", side === "left");
    var b = $("btn-dock");
    if (b) b.textContent = "Dock: " + side;
  }

  document.addEventListener("DOMContentLoaded", function () {
    showSession();
    var wrap = $("face-wrap");
    if (window.Avatar && window.Avatar.ImageRenderer && wrap) {
      face = new window.Avatar.ImageRenderer(wrap);
    } else {
      var cv = $("avatar-canvas");
      if (cv) cv.classList.remove("hidden");
      if (wrap) wrap.classList.add("hidden");
      face = (window.Avatar && window.Avatar.Renderer2D && cv) ? new window.Avatar.Renderer2D(cv) : null;
    }
    avatarEvent({ event: "IDLE" });

    Array.prototype.forEach.call(document.querySelectorAll("#viewbar button"), function (b) {
      b.onclick = function () { setView(b.getAttribute("data-view")); };
    });
    var dock = $("btn-dock");
    if (dock) dock.onclick = function () {
      setDock(document.body.getAttribute("data-dock") === "right" ? "left" : "right");
    };
    var compact = $("btn-compact");
    if (compact) compact.onclick = function () { document.body.classList.toggle("compact"); };
    var tts = $("btn-tts");
    if (tts) tts.onclick = function () { setTts(!ttsOn); };
    var call = $("btn-call");
    if (call) call.onclick = toggleCall;
    var b3d = $("btn-3d");
    if (b3d) b3d.onclick = function () { set3d(!view3d); };

    var input = $("text-input");
    var go = function () {
      var v = input ? input.value.trim() : "";
      if (v) { input.value = ""; send(v); }
    };
    var sendBtn = $("btn-send");
    if (sendBtn) sendBtn.onclick = go;
    if (input) input.addEventListener("keydown", function (e) { if (e.key === "Enter") go(); });

    var mic = $("btn-mic");
    if (mic) {
      mic.addEventListener("mousedown", startPtt);
      mic.addEventListener("mouseup", stopPtt);
      mic.addEventListener("mouseleave", stopPtt);
      mic.addEventListener("touchstart", function (e) { e.preventDefault(); startPtt(); });
      mic.addEventListener("touchend", stopPtt);
    }
    document.addEventListener("keydown", function (e) {
      if (e.code === "Space" && e.target !== input && !e.repeat) {
        e.preventDefault();
        startPtt();
      }
    });
    document.addEventListener("keyup", function (e) {
      if (e.code === "Space" && e.target !== input) {
        e.preventDefault();
        stopPtt();
      }
    });

    initVoice();
    document.addEventListener("aetherius-avatar-event", function (e) {
      if (e && e.detail) avatarEvent(e.detail);
    });
    pollHealth(); pollState(); pingBridge();
    setInterval(pollHealth, 5000);
    setInterval(pollState, 10000);
    setInterval(pingBridge, 15000);
    setInterval(pollBridgeEvents, 5000);
    startEvents();
    transcript("system", "dashboard ready · session " + sessionId +
      " · sup " + (SUP_BASE || "same-origin") + " · bridge " + BRIDGE_BASE, "sys");
  });

  window.BridgeUI = {
    sessionId: function () { return sessionId; },
    setView: setView,
    setDock: setDock,
    applyAvatarEvent: avatarEvent,
    set3d: set3d,
    send: send
  };
})();
