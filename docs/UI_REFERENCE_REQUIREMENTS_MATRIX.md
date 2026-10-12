# UI REFERENCE REQUIREMENTS MATRIX — SUPERVISOR_UI_M2
Source: owner directive 2026-10-12 23:36 (§4–§14, §41) + prior NOVA / NEXUS / OE /
Aetherius reference screenshots described in the owner's messages.

Owner's screenshots were pasted in-conversation and are not on disk; the
directive text is the authoritative spec and is transcribed here. Every row is
a QA criterion — the visual QA loop (§15) scores the UI against this matrix
after each increment.

## TARGET: UI-F4 minimum (§16). Current assessed level: UI-F1 (engineering scaffold).

## 1. VISUAL LANGUAGE (§13)
| ID | Requirement | QA check |
|----|-------------|----------|
| VL-1 | Dark navy/black base | base surface is near-black/navy, not grey-white |
| VL-2 | Cyan/blue luminous edges | borders/accents glow cyan-blue |
| VL-3 | Subtle glass surfaces | panels have translucency + blur, not flat fills |
| VL-4 | High information density | mission-control density without clutter |
| VL-5 | Strong spatial hierarchy | clear zones: nav / content / inspector |
| VL-6 | Large character imagery | avatars are prominent, not 16px icons |
| VL-7 | Clean technical typography | mono for IDs/SHAs, sans for prose |
| VL-8 | Controlled neon accents | accents are purposeful, not decorative noise |
| VL-9 | Existing themes retained | ABYSS AURORA EMBER GRAPHITE FROST all work |
| VL-10 | NOT generic Bootstrap/admin | no default-table-with-bootstrap look |

## 2. AVATAR-FIRST WORKFORCE (§4)
| ID | Requirement | QA check |
|----|-------------|----------|
| AV-1 | Large worker/avatar cards | avatar ≥ 96px on worker card |
| AV-2 | Worker portrait + role/title | name + role visible without hover |
| AV-3 | Current project + task on card | both visible at card level |
| AV-4 | Activity/state indicator | live state dot with colour semantics |
| AV-5 | Model/provider on card | shown |
| AV-6 | Quota/reset on card | shown with reset time when WAITING_FOR_QUOTA |
| AV-7 | Progress/evidence | task progress or evidence summary |
| AV-8 | Direct worker interaction | click → message/continue/inspect |
| AV-9 | Six presentation modes | COMPACT CARD / TEAM TILE / FULL WORKER VIEW / CONFERENCE TILE / VOICE-CALL VIEW / DETAIL INSPECTOR all reachable |

## 3. NAVIGATION (§5)
Primary areas, coherent not mechanical:
HOME/MISSION CONTROL · CHAT · WORK · PROJECTS · TEAMS · AGENTS · CONFERENCE ·
CALLS · TASKS · KNOWLEDGE · FILES · APPS · MODELS · QUOTAS/USAGE · GIT/REPOS ·
RESEARCH · SECURITY · SETTINGS

QA: persistent nav shell; every area reachable; active state obvious; keyboard
navigable; no dead ends.

## 4. MISSION CONTROL HOME (§6)
Must expose at a glance: PROGRAMME COMPLETION · ACTIVE PROJECTS · PROJECT
MILESTONES · ACTIVE WORKERS · IDLE WORKERS · WAITING_FOR_QUOTA · BLOCKED ·
QA QUEUE · HANDOFF QUEUE · READY TASKS · CRITICAL GAPS · SYSTEM RESOURCES ·
QUOTA CAPACITY · GIT HEALTH · TEST HEALTH · RESEARCH INGESTION · SECURITY STATUS

QA: all 17 tiles present, each sourced from a LIVE_VERIFIED fact; an absent
source renders NOT_EXPOSED (never 0).

## 5. TEAM ROOM (§7)
Hermes Supervisor + 5–8 internal subagents + OpenCode + Codex + commissioned
externals. Tile shows: avatar name role project task phase status
last-activity model application quota write-ownership.
Actions: click / talk / inspect / view task / view files / view tests /
continue / pause / reassign / change model / open application.

## 6. CONFERENCE VIEW (§8)
all-active / project-filtered / team-filtered / status-filtered. LIVE mode =
REAL workers only. Demo mode = unmistakably labelled fixtures. No fabricated
active speakers.

## 7. FULL WORKER VIEW (§9)
large avatar · identity · role · parent supervisor · application · model ·
provider · plan · quota · reset · current task · project · milestone ·
progress evidence · files · worktree · branch · commit · tests · tools ·
timeline · messages · handoffs · gaps · blockers · resource consumption.
Controls: MESSAGE CONTINUE PAUSE RESUME REASSIGN CHANGE-MODEL OPEN-APP
OPEN-WORKSPACE VIEW-DIFF RUN-QA.

## 8. INTER-AGENT MESSAGING (§10)
Real structured messages (Hermes→OpenCode, H-SA-Research→Codex, …) with
human-readable translation over the machine event. No fabricated conversations.

## 9. WORK / IDE SURFACE (§11)
project tree · source files · terminal · tests · problems · Git · agent panel ·
worker avatar · current task · evidence. Reusable by Aetherius IDE later.

## 10. CALLS (§12)
Architectural seams for text/voice/video/screen-share/worker-call/group.
Honest states only: AVAILABLE / NOT_IMPLEMENTED / OFFLINE / DEFERRED_INTERFACE.
Do NOT fake live calls.

## 11. SUPERVISOR HEALTH BAR (§38)
Supervisor: LIVE · Last cycle: Ns ago · Workers monitored: N · Ready tasks: N ·
Assignments this hour: N · Missed idle events: N · Watchdog: LIVE

## 12. LIVE vs DESIGN MODE (§39)
Visible switch. LIVE = real workers/states only. DESIGN = labelled fixtures.
Never mixed.

## SCORING (per §42, after each increment)
visual hierarchy · avatar integration · information density · polish ·
navigation · worker legibility · mission-control usefulness · interaction
quality · accessibility · responsiveness — 1–5 each, recorded with the commit.

## UI-F LEVEL DEFINITIONS (§16)
F0 debugging/scaffold · F1 functional · F2 coherent product UI · F3 polished
professional · F4 reference-quality production · F5 final design-system quality.
**Acceptance requires ≥ F4.**
