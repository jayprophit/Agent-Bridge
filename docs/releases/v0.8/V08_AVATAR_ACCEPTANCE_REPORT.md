# v0.8 Avatar Acceptance Report (convergence, measured)

## Real Three.js browser acceptance: PASS

`tests.test_ui_acceptance`, real headless Edge over loopback: **6/6 in
96.652s**. Canvas rendered, procedural GLB loaded (Head/Jaw/EyeL/EyeR),
avatar visible, states THINKING/EMOTION/SPEAKING/VISEME/SUCCESS/
TOOL_RUNNING applied, screenshot >10KB. No external asset, no download
(three.js vendored). GLB: 12272 bytes, magic `glTF`.

## Protocol: PASS

14 events, 6 expressions, 15 visemes with jaw table, MALE/FEMALE/
NEUTRAL/CUSTOM presentations (never inferred from voice).

## Lip sync truth

Mode: **AUDIO_AMPLITUDE_FALLBACK**. System.Speech exposes no
per-phoneme timestamps here, so the viseme table drives the Jaw node.
NOT described as phoneme-perfect.

## Character creator: PASS (architecture)

8 creation modes, SIMPLE + ADVANCED views, 26 appearance categories,
voice/personality/expression independent, undo/redo/reset/save/
duplicate/version history. Geometry morphs: PROFILE_SUPPORTED stored,
RENDERED_SUPPORTED only for procedural nodes, true morphs
PROVIDER_REQUIRED (never faked).

## Guided capture: PASS (fixtures)

7 guided views in order, camera permission required, ephemeral raw
frames, derive-then-delete default PROVEN (files gone), explicit retain
audited, photo upload contract, reconstruction PROVIDER_REQUIRED.

## Chat/Work: PASS

Same session survives Chat->Work->Chat, dock left/right, compact avatar
in Work, no second agent instance (browser-verified).

**Status: PASS**
