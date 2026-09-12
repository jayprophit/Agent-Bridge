# Three.js Reference UI (v0.8, Part H)

`ui/` is static (index.html + app.js + avatar.js): Chat and Work views share
ONE session id (switching never mints a new session — asserted by test),
agent panel docks left/right with adjustable width, compact avatar mode in
Work view. Avatar renderer defaults to the offline 2D canvas fallback;
`useThreeRenderer()` swaps in Three.js + reference-avatar.glb when the host
provides `window.THREE` — same event API either way. Backend runs headless
with no avatar. No external model assets in the tree.
