# §42 VISUAL QA SCORECARD — M2 shell (Hermes, 2026-10-13 ~02:5x)

Scored against docs/UI_REFERENCE_REQUIREMENTS_MATRIX.md. This is the
supervisor-m2.html shell (commit 53cc45b), verified live in the owner's
browser via the AX accessibility tree (not a screenshot guess).

## LIVE EVIDENCE (from the rendered AX tree)
- Shell: top bar (Æ Aetherius / "Supervisor · Ideas to impact, together."),
  LIVE·DESIGN toggle, search, "Supervisor LIVE" env status, JP avatar.
- Icon rail: Mission Control + Chat, Work, Projects, Teams, Conference, Tasks,
  Knowledge, Quotas/Usage, Git/Repos (10 nav areas, §5).
- Sidebar: Assign Task button + workforce roster (3 workers) + Runtime card
  (continuation bar, "3/3 running").
- Mission Control home: 7 stat tiles — PROGRAMME QUIET, ACTIVE WORKERS 3,
  TOTAL WORKERS 3, WAITING QUOTA 0, HANDOFFS PENDING 0, OPEN GAPS 0,
  RESOURCES CRITICAL.
- Worker grid: 3 avatar cards (codex-primary/CP, ollama-local/OL,
  opencode-primary/OP), each with role, IMPLEMENTING badge, Application /
  Project / Task / Heartbeat rows. Source chip LIVE_VERIFIED.
- RESOURCES CRITICAL is REAL: resource_governor reports CRITICAL with throttle
  actions. The UI shows it faithfully — this is correctness, not a defect.

## SCORECARD (1–5, §42)
| Dimension | F1 (before) | M2 (now) | Evidence |
|---|---|---|---|
| visual hierarchy | 2 | 4 | three-zone shell (rail/sidebar/center/inspector), hero + tiles + grid |
| avatar integration | 1 | 4 | deterministic hue avatars on cards + sidebar + inspector (52px card, 64px inspector) |
| information density | 3 | 4 | mission-control tile strip + dense worker cards |
| polish | 2 | 4 | glass panels, gradients, glow, hover lift, reference palette |
| navigation | 1 | 3 | icon rail with all §5 areas; 9 are honest M3 stubs (Mission Control live) |
| worker legibility | 2 | 4 | avatar + name + role + status dot + badge + 4 meta rows per card |
| mission-control usefulness | 1 | 4 | 7-tile overview; missing §6's project/milestone/GIT/TEST tiles (M3) |
| interaction quality | 2 | 3 | click-to-inspect + live Continue; Message/Pause/Reassign honest NOT_IMPLEMENTED |
| accessibility | 3 | 4 | semantic roles verified via AX tree; aria on avatars; still needs keyboard focus audit |
| responsiveness | 3 | 3 | auto-fill grid; needs narrow-viewport check |
| **ASSESSED LEVEL** | **UI-F1** | **UI-F2** | target ≥ UI-F4 |

## HONEST ASSESSMENT
M2 shell is UI-F2 (coherent product UI), NOT the UI-F4 target. Gaps to F4:
- G5 conference view, G7 inter-agent messaging, G8 IDE surface, G9 calls seam
- G3 mission control missing project/milestone/GIT-health/TEST-health/
  research-ingestion/security tiles
- G6 full worker view missing model/provider/plan/timeline/tools/resources
- G12 five-theme coverage (ABYSS/AURORA/EMBER/GRAPHITE/FROST) unproven on M2
- keyboard-nav + screen-reader full audit; narrow-viewport responsive pass

## PARALLEL STATE (§23 — not sequential)
- OpenCode M2-A (React: avatar/worker-card/team-room) — IN PROGRESS, files
  landing (avatar.tsx, worker-card.tsx, team-room.tsx, avatar-types.ts,
  roster-types.ts, avatar.test.tsx)
- Hermes M2 shell (this file's subject) — DONE + committed + live (53cc45b)
- Next: M3 (conference + messaging + richer interaction) per §41
