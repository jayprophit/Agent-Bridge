# Avatar Architecture (v0.8, Part G)

DefaultAgent -> Avatar Event Protocol -> renderer. The avatar is
presentation only; any model/agent drives the same avatar. Assets are
replaceable glTF/GLB (VRM where practical); the tree ships a 12KB
procedural reference humanoid (`ui/assets/reference-avatar.glb`, 10 named
nodes incl. Jaw/EyeL/EyeR targets) — no downloads, no copyrighted models.
See AVATAR_EVENT_PROTOCOL.md, THREEJS_REFERENCE_UI.md.
