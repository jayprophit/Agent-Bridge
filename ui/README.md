# Aetherius Supervisor UI

Single-page dashboard (vanilla JS, no build step). Served same-origin by
`scripts/serve_supervisor_dashboard.py` (`GET /ui/`), talking to the supervisor
API on the same origin and to the Agent-Bridge session API over CORS.

## Run

```
python scripts/serve_supervisor_dashboard.py --port 8472 --ui-root ui
# UI: http://127.0.0.1:8472/ui/
```

Live data requires the supervisor daemon:

```
compute\supervisor_runtime.cmd            # or the Startup shortcut
```

## URL parameters

| param | default | meaning |
|---|---|---|
| `sup` | same-origin | supervisor API base |
| `bridge` | `http://127.0.0.1:8471` | Agent-Bridge base |
| `portal` | `http://127.0.0.1:9119` | Hermes portal base (used by registry placeholders) |
| `profile` | `aetherius-build` | profile for `{profile}` placeholders |

## Embedding (IDE / Genesis / Aetherius OS)

`window.BridgeUI` is the integration surface:

```js
BridgeUI.sessionId()            // current session id (persisted in localStorage)
BridgeUI.setView("chat|work|team|monitor")
BridgeUI.setDock("left|right")
BridgeUI.set3d(true)
BridgeUI.applyAvatarEvent({ event: "THINKING" })   // IDLE/LISTENING/SPEAKING/THINKING/WORKING/ERROR/APPROVAL
BridgeUI.selectAgent("opencode-primary")           // opens detail panel; null deselects
BridgeUI.openPortal("aetherius-supervisor")        // embed modal for registered portals
BridgeUI.send("text")                              // same path as the input row
```

Avatars elsewhere can drive the dashboard by dispatching on `document`:

```js
document.dispatchEvent(new CustomEvent("aetherius-avatar-event",
  { detail: { event: "SPEAKING" } }));
```

## Per-agent portals (`agent_portals.json`)

Keyed by `worker_id`; keys ending in `*` match by prefix. `url` supports
`{profile}`, `{worker}`, `{host}` placeholders. `embed: false` forces a new tab.

```json
{ "portals": { "hermes-*": { "label": "Hermes portal", "embed": true,
  "url": "http://127.0.0.1:9119/chat?profile={worker}" } } }
```

Embed modal notes: the embedded app may steal keyboard focus (it is an iframe),
so `Escape` only closes when focus is in the parent — the modal always offers
Close and "Open in new tab". Closing resets the iframe to `about:blank` to stop
portal traffic.

## Files

| file | role |
|---|---|
| `index.html` | shell, styles, embed modal, importmap (`three` → `vendor/`) |
| `app.js` | controller: polls, SSE, roster/team/monitor, detail, portals, voice, TTS, BridgeUI |
| `avatar.js` | `ImageRenderer` (face state images) + legacy 2D renderer |
| `avatar-three.js` | three.js GLB renderer, jaw/gaze sync, viseme lip-sync |
| `agent_portals.json` | per-agent dashboard registry |
| `assets/` | face state images, reference art, `reference-avatar.glb` |
| `vendor/` | `three.module.js`, `GLTFLoader.js` |

## QA

Headless: `node ~/.claude/skills/browser-automation/browser.mjs http://127.0.0.1:8472/ui/ --script <qa>.mjs`

Expected console error when Agent-Bridge is down: one `ERR_CONNECTION_REFUSED`
to `127.0.0.1:8471` (by design, degraded send queues messages locally).
