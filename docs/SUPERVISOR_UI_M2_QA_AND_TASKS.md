# SUPERVISOR_UI_M2 — VISUAL QA SCORECARD + GAP LIST + TASK ASSIGNMENTS
QA run by Hermes 2026-10-12 23:45 (§15/§42). Reference: docs/UI_REFERENCE_REQUIREMENTS_MATRIX.md

## CURRENT STATE (measured, not guessed)
- supervisor-ui: 2,415 LOC, 17 files
- sections rendered: repositories, local_models, team_registry, workers,
  supervision, resources, knowledge, hive, opencode, codex (10)
- avatars: 0 · nav shell: 0 · mission control: 0 · conference: 0 · messaging: 0
- worker presentation: table rows + one click-through detail panel

## SCORECARD (1–5, per §42)
| Dimension | Score | Evidence |
|---|---|---|
| visual hierarchy | 2 | sections stack vertically; no nav/zones |
| avatar integration | 1 | zero avatars anywhere |
| information density | 3 | facts are dense but undifferentiated |
| polish | 2 | functional cards/tables; debug-screen feel |
| navigation | 1 | single scrolling page, no nav shell |
| worker legibility | 2 | table rows; state is a text cell |
| mission-control usefulness | 1 | no mission-control home |
| interaction quality | 2 | one click-to-inspect + continue |
| accessibility | 3 | a11y tests pass (inherited from OpenCode's work) |
| responsiveness | 3 | basic responsive grid |
| **ASSESSED LEVEL** | **UI-F1** | target ≥ UI-F4 |

## GAP LIST (ordered by owner-stated priority)
G1  NO AVATAR SYSTEM — workers are rows, not team members. (§4 AV-1..AV-9)
G2  NO NAVIGATION SHELL — no HOME/CHAT/WORK/PROJECTS/TEAMS/AGENTS/CONFERENCE/
    CALLS/TASKS/KNOWLEDGE/FILES/APPS/MODELS/QUOTAS/GIT/RESEARCH/SECURITY/
    SETTINGS. (§5)
G3  NO MISSION CONTROL HOME — the 17 owner-overview tiles don't exist. (§6)
G4  NO TEAM ROOM — no tiles with avatar/role/project/task/quota/write-ownership
    and the 11 worker actions. (§7)
G5  NO CONFERENCE VIEW. (§8)
G6  NO FULL WORKER VIEW — current detail panel lacks avatar/plan/milestone/
    timeline/tools/resources and most controls. (§9)
G7  NO INTER-AGENT MESSAGING. (§10)
G8  NO WORK/IDE SURFACE. (§11)
G9  NO CALLS SEAM (even honest NOT_IMPLEMENTED states). (§12)
G10 NO SUPERVISOR HEALTH BAR (live/last-cycle/workers/ready/missed-idle/
    watchdog). (§38)
G11 NO LIVE↔DESIGN MODE SWITCH. (§39)
G12 THEME COVERAGE UNPROVEN for ABYSS/AURORA/EMBER/GRAPHITE/FROST on the new
    components. (§13 VL-9)

## PARALLEL TASK ASSIGNMENTS (§23 — do NOT execute sequentially)

### T-UI-1 → OpenCode (primary implementer, isolated worktree)
SUPERVISOR_UI_M2-A: AVATAR SYSTEM + WORKER CARDS + TEAM ROOM
- Deterministic avatar generator (no network): initials + hue-from-worker-id +
  role glyph, SVG, ≥96px card / ≥160px full view. Must be themeable and pass
  a11y (aria-label = worker name+role, decorative=false).
- WorkerCard component: avatar, name, role, project, task, state dot (colour
  semantics from tokens), model, quota+reset, write-ownership, progress.
- TeamRoom view: grid of WorkerCards for the LIVE roster; filter by
  status/project/team; all 11 worker actions wired where a real endpoint
  exists (continue is live today; others emit an honest
  NOT_IMPLEMENTED/DEFERRED_INTERFACE state — never a fake success).
- Reuse: components/roster.tsx data path, api/client.ts (add fetchers there
  ONLY — bounds.test.ts forbids fetch outside client.ts), tokens/tokens.css
  (add avatar tokens; no raw colours anywhere).
- Acceptance: tsc 0; all existing 97 tests still pass; ≥12 new tests; renders
  the 3 real workers with avatars in LIVE mode; visual scorecard re-run.

### T-UI-2 → OpenCode (same worktree, sequential after M2-A)
SUPERVISOR_UI_M2-B: NAV SHELL + MISSION CONTROL HOME
- Persistent nav shell with the §5 area list; active-state; keyboard nav.
- MissionControl home with the 17 §6 tiles, each a LIVE_VERIFIED fact or an
  honest NOT_EXPOSED (never 0-from-nothing).
- Supervisor health bar (§38) fed from /v1/supervisor/health + checkpoint
  cycles + watchdog.log presence.
- LIVE↔DESIGN switch (§39) with unmistakable demo labelling.

### T-ARCH-1 → H-SA-ARCH (Hermes internal)
Reuse architecture for M3/M4: conference grid + messaging + IDE surface must
be one component family with the avatar system, not three one-offs. Deliver a
short ADR in docs/ (component tree, state ownership, which seams are
DEFERRED_INTERFACE) BEFORE OpenCode starts M2-C.

### T-QA-1 → H-SA-QA (Hermes internal)
Visual QA harness: script the §42 scorecard against the running UI (render,
screenshot, DOM assertions on avatar presence/nav landmarks/contrast), so
every future increment is scored automatically rather than by eye.

### T-RES-1 → H-SA-RESEARCH (Hermes internal)
Register the owner's reference images if they can be recovered from session
history; otherwise confirm the directive-derived matrix is complete and flag
any visual detail present only in the images.

### T-DEV-1 → H-SA-DEVOPS (Hermes internal)
§36/§37: progress-based idle detection. A worker nominally RUNNING with no
new session-advance/file-write/commit for N cycles must raise
WORKER_IDLE_REVIEW, not stay silent. Root cause of SUPERVISOR_MISSED_IDLE_EVENT.

### T-PROV-1 → H-SA-PROVENANCE (Hermes internal)
Extend the 352-fork registry: for the 63 PARTIAL_REUSE forks, record a
concrete reuse decision per project (what would be taken, what is
LICENCE_INCOMPATIBLE, what is REDUNDANT) — "accounted for" is not yet
"dispositioned with a decision".

## DEFINITION OF DONE for M2 (§41)
polished nav shell · avatar worker cards · real workforce team view · full
worker inspector · live status/quota · project/task queue · handoffs · gap
queue · supervisor health · resource monitor · Git/test evidence · responsive
layouts · theme integration (all 5 themes) · accessibility · LIVE/DEMO
separation. Then M3 = conference+messaging, M4 = IDE/workspace. M1 is NOT final.
