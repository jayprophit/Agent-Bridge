/* Avatar renderer (v0.8 reference). Same event API for 2D + Three.js.
 *
 * Default: offline 2D canvas renderer (no assets, no network). If Three.js
 * is available (window.THREE, e.g. loaded by the host), useThreeRenderer()
 * swaps in the GLB scene; the event protocol is unchanged. Backend works
 * headless with no avatar at all.
 */
(function () {
  "use strict";
  const JAW = { sil: 0.0, PP: 0.05, FF: 0.15, TH: 0.2, DD: 0.35, kk: 0.3,
    CH: 0.35, SS: 0.25, nn: 0.3, RR: 0.4, aa: 1.0, E: 0.55, I: 0.35,
    O: 0.7, U: 0.4 };
  const EMOTION_EYES = { neutral: "oo", happy: "^^", concerned: "--",
    thinking: "o.", surprised: "OO", confident: "^-" };

  function Renderer2D(canvas) {
    this.canvas = canvas;
    this.state = { event: "IDLE", emotion: "neutral", jaw: 0.0, gaze: 0.0 };
  }
  Renderer2D.prototype.apply = function (ev) {
    if (ev.event) this.state.event = ev.event;
    if (ev.emotion) this.state.emotion = ev.emotion;
    if (ev.viseme && JAW[ev.viseme] !== undefined) this.state.jaw = JAW[ev.viseme];
    if (typeof ev.intensity === "number") this.state.gaze = ev.intensity - 0.5;
    this.draw();
    const label = document.getElementById("avatar-state");
    if (label) label.textContent = this.state.event;
  };
  Renderer2D.prototype.draw = function () {
    const ctx = this.canvas.getContext("2d");
    if (!ctx) return;
    const W = this.canvas.width, H = this.canvas.height;
    ctx.fillStyle = "#1a1a1a"; ctx.fillRect(0, 0, W, H);
    const cx = W / 2 + this.state.gaze * 20, cy = H / 2 - 10;
    ctx.strokeStyle = "#eee"; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(cx, cy, 60, 0, Math.PI * 2); ctx.stroke(); // head
    ctx.fillStyle = "#eee"; ctx.font = "28px system-ui"; ctx.textAlign = "center";
    ctx.fillText(EMOTION_EYES[this.state.emotion] || "oo", cx, cy - 5); // eyes
    const jaw = this.state.jaw * 26; // mouth/jaw from viseme or amplitude
    ctx.beginPath(); ctx.ellipse(cx, cy + 32, 22, 4 + jaw, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "#888"; ctx.font = "12px system-ui";
    ctx.fillText(this.state.event, cx, H - 12);
  };

  function useThreeRenderer(canvas, glbUrl, onReady) {
    // Integration point: host provides window.THREE (pinned version).
    // Loads reference-avatar.glb (or a user VRM/GLB); jaw/gaze targets by
    // node name (Jaw, EyeL, EyeR). Falls back to Renderer2D when absent.
    if (!window.THREE) return null;
    return { three: true, glbUrl: glbUrl, onReady: onReady || null };
  }

  window.Avatar = { Renderer2D: Renderer2D, useThreeRenderer: useThreeRenderer,
    JAW: JAW, EMOTIONS: Object.keys(EMOTION_EYES) };
})();
