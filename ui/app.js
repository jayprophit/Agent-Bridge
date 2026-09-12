/* Reference UI controller (v0.8). Chat <-> Work share ONE session.
 * Switching views never creates a new agent/session: session id persists.
 */
(function () {
  "use strict";
  let sessionId = "session-" + Math.random().toString(36).slice(2, 10);
  let renderer = null;

  function sid() { return sessionId; }
  function show(id) { document.getElementById("session-id").textContent = id; }

  function setView(name) {
    document.body.setAttribute("data-view", name);
    document.getElementById("chatview").classList.toggle("hidden", name !== "chat");
    document.getElementById("workview").classList.toggle("hidden", name !== "work");
    document.body.classList.toggle("compact", name === "work");
    // Session MUST survive the switch.
    show(sessionId);
  }

  function setDock(side) {
    document.body.setAttribute("data-dock", side);
    document.body.classList.toggle("dock-left", side === "left");
    document.getElementById("btn-dock").textContent = "Dock: " + side;
  }

  function applyAvatarEvent(ev) {
    if (renderer) renderer.apply(ev);
    const tools = document.getElementById("tools");
    if (ev.event === "TOOL_RUNNING" && tools) tools.textContent = "tools: running";
    if (ev.event === "IDLE" && tools) tools.textContent = "tools: idle";
  }

  function send(text) {
    const t = document.getElementById("transcript");
    if (t) {
      const div = document.createElement("div");
      div.textContent = "you [" + sessionId + "]: " + text;
      t.appendChild(div);
    }
    // Local API wiring point: POST /v1/sessions/{id}/tasks with sessionId.
  }

  document.addEventListener("DOMContentLoaded", function () {
    show(sessionId);
    const canvas = document.getElementById("avatar-canvas");
    const three = window.Avatar.useThreeRenderer(canvas, "assets/reference-avatar.glb");
    renderer = three || new window.Avatar.Renderer2D(canvas);
    renderer.apply({ event: "IDLE" });
    document.getElementById("btn-chat").onclick = function () { setView("chat"); };
    document.getElementById("btn-work").onclick = function () { setView("work"); };
    document.getElementById("btn-dock").onclick = function () {
      setDock(document.body.getAttribute("data-dock") === "right" ? "left" : "right");
    };
    document.getElementById("btn-compact").onclick = function () {
      document.body.classList.toggle("compact");
    };
    const input = document.getElementById("text-input");
    const go = function () { if (input.value.trim()) { send(input.value.trim()); input.value = ""; } };
    document.getElementById("btn-send").onclick = go;
    input.onkeydown = function (e) { if (e.key === "Enter") go(); };
  });

  window.BridgeUI = { sessionId: sid, setView: setView, setDock: setDock,
    applyAvatarEvent: applyAvatarEvent };
})();
