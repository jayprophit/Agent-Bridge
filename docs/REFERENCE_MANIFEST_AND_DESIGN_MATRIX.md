# REFERENCE MANIFEST + DESIGN MATRIX
Ingested by Hermes 2026-10-13 (§4/§5/§6/§7). All four reference directories
recursively catalogued. This is the design-source repository for the canonical
Supervisor UI merge.

## SOURCES INGESTED (72 files total, deduplicated)
| ref_id | path | type | purpose |
|---|---|---|---|
| VIBE-* | IDE-Workspace-dashboard/references/vibe-prototype/aetherius-ide/ | **WORKING REACT APP (43 files, 10,005 LOC)** | THE "video attempt" — a complete animated Aetherius IDE prototype. Real components, not screenshots. |
| VIS-IDE-* | Genesis/references/visuals/ide/ (19 PNG) | images | Aetherius/NEXUS/NOVA/OE visual language |
| VIS-IMG-* | Genesis/references/visuals/images/ (10 JPG) | images | Aetherius OS / Human Experience / architecture |
| VIS-DASH-* | IDE-Workspace-dashboard/references/visuals/ (18 PNG) | images | Aetherius IDE 3-col shell + team/conference |

## THE VIBE PROTOTYPE = THE VIDEO ATTEMPT (§6)
No mp4/webm/mov/gif exists on disk. The "previous video attempt visually closer
to the generated images" IS this vibe-prototype: a live React app using
`motion` (Framer Motion) for transitions, `d3` for charts, `lucide-react` icons.
Its animated behaviour (pulse-glow avatar, orbit, wave, view transitions) is the
motion the static screenshots cannot show. Analysed as source, not embedded.

### VIBE DESIGN DNA (extracted from actual code)
- **Fonts:** Plus Jakarta Sans (UI) + Fira Code (mono), 13px base, -0.01em tracking
  ("VS Code, Devin & Antigravity metric scale")
- **Palette (from 1,700+ Tailwind classes):**
  - base: `slate-950` (#020617) / `slate-900` / `slate-800`, meeting bg `#070b14`
  - accent-primary: `cyan-400` (111×) / `cyan-300` / `cyan-500`
  - accent-secondary: `blue-600` (77×) / `blue-500` / `blue-400`
  - success: `emerald-400` (58×) / `emerald-500`
  - danger/live: `rose-400` / `rose-600` / `rose-500` (LIVE badge = rose ping)
  - warning: `amber-400`
  - text: `slate-400` (236×) / `slate-200` / `slate-300` / `slate-500` / `slate-100`
  - border: `slate-800` (206×) / `slate-700`
- **Motion keyframes:** `pulseGlow` (avatar, drop-shadow cyan→indigo, 4s),
  `orbitSpin` (20s/25s reverse), `waveOscillate` (voice bars 6→28px)
- **Layout:** 13px dense, 6px thin scrollbars, overflow-hidden app shell

### VIBE COMPONENT TREE (real, reusable mechanisms)
| component | LOC | mechanism to port |
|---|---|---|
| CodeEditor | 1070 | editor surface + syntax theme |
| TerminalPanel | 887 | terminal + themes |
| App | 766 | view-mode shell, keybindings, modal orchestration |
| VersionControlPanel | 676 | Git status surface |
| VSCodeSidePanel | 548 | file tree + inspector |
| TaskCompletionTrendChart | 546 | d3 telemetry chart |
| ToolsDrawer | 519 | tool/model selector |
| ChatPanel | 450 | agent chat + message list |
| InteractivePreview | 420 | live preview surface |
| PerformanceDashboardModal | 403 | CPU/RAM/GPU resource gauges |
| AgentSidePanel | 387 | agent detail + controls |
| TeamMeetingView | 306 | **conference**: LIVE badge, speaking queue, inter-agent chat, gallery |
| TeamSidePanel | 210 | team roster |
| AvatarHologram | ~150 | **glowing avatar** (pulse-glow + orbit rings) |
| SidebarRail | ~150 | icon nav (Home/Projects/Git/Templates/Integrations/Deployments) |
| Header | 310 | top bar + model selector + theme |
| CommandPaletteModal | 178 | ⌘K palette |
| ProjectsDrawer | 193 | project list |

### VIBE DATA SHAPE (TeamAgent — maps to our WorkerRecord)
id · name · role · specialty · avatarUrl · status(active/in_call) ·
currentTask · recentActivity · speaking · speechText
→ Our live WorkerRecord has: worker_id · application · role · worker_type ·
status · task_description · project · model · quota_state · last_heartbeat.
Avatar: prototype uses unsplash URLs; we keep the DETERMINISTIC hue-avatar
(no network, §49) — same visual role, honest source.

## VISUAL LANGUAGE CONSENSUS (images + prototype, §7)
dark navy/black base · cyan/electric-blue luminous edges · purple/indigo
secondary · glass layered panels · dense structured info · large avatar presence
· technical typography (Plus Jakarta + Fira Code) · command-centre hierarchy.
NOT literal pixel-copy; the recurring mechanisms above are the spec.

## TARGET COMPONENT MAP (§18 design system, ported into React)
AetheriusShell · TopBar · IconRail · ContextSidebar · GlassPanel · MetricTile ·
WorkerCard · Avatar(hologram-glow variant) · StatusChip · QuotaMeter ·
ResourceMeter · TaskCard · ProjectCard · ConferenceTile · MessageFeed ·
Inspector · EvidenceList · HandoffCard · GapCard · GitStatus · TestStatus ·
ModelSelector.

## MERGE DECISION (§2/§31)
Canonical = React `supervisor-ui.html` (has the tested client + SourceFact +
controls + bounds tests). M2 shell's visual strengths (top bar, icon rail,
mission-control tiles, navy/cyan palette, density) PORT INTO React. The vibe
prototype supplies the F4 polish (glass, glow, motion, conference, gauges).
`supervisor-m2.html` becomes a redirect to `supervisor-ui.html` after merge.
