# AETHERIUS-HUMAN-RUNTIME-APPLICATION-VALIDATION

## Status: ACTIVE - OWNER REQUIREMENT

**Added**: 2026-09-17
**Priority**: GLOBAL COMPLETION REQUIREMENT
**Scope**: All Aetherius user-facing applications

## Summary

For user-facing software:

**SOURCE EXISTS ≠ PRODUCT WORKS**
**BUILD PASSES ≠ PRODUCT WORKS**
**UNIT TESTS PASS ≠ PRODUCT WORKS**
**UI LAUNCHES ≠ PRODUCT WORKS**
**SCREENSHOT LOOKS GOOD ≠ PRODUCT WORKS**

The product must be:

**LAUNCHED → USED → OBSERVED → STRESSED → BROKEN SAFELY → RECOVERED → FIXED → RETESTED**

from the perspective of an actual human user.

## Applies To

- Aetherius OS/OE
- Every Aetherius first-party application
- Aetherius IDE
- Agent Bridge
- Genesis and its user-facing interfaces
- Universal-Bridge
- Poietek
- MAT
- ATHENA
- Future Office applications
- Creative applications
- CAD/engineering applications
- Simulation applications
- Science applications
- Communication applications
- Media applications
- Games
- Utilities
- Security applications
- Accessibility applications
- App Store
- Settings/system applications
- Plugins/extensions where they expose UI
- Every future first-party Aetherius product with a user-facing interface

## Core Principles

### 1. Test Like a Real Human, Not Only Like a Test Runner

Automated tests are necessary. They are NOT sufficient.

For every runnable user-facing application, you must actually:
- LAUNCH IT
- LOOK AT IT
- INTERACT WITH IT
- CLICK IT
- TYPE INTO IT
- NAVIGATE IT
- CREATE REAL TEST DATA
- EDIT IT
- SAVE IT
- CLOSE IT
- REOPEN IT
- USE ITS MENUS
- USE ITS TOOLBARS
- USE ITS SETTINGS
- TRIGGER ITS FEATURES
- TRIGGER ERRORS
- RECOVER FROM ERRORS

and judge the resulting experience from a human user's point of view.

### 2. Human Testing is Black-Box + White-Box

Use BOTH perspectives.

**WHITE-BOX**: Inspect source, architecture, logs, exceptions, tests, internal state, databases, APIs, IPC, dependencies.

**BLACK-BOX / HUMAN**: Act as though you know nothing about the implementation. Ask: "If I installed this product today, could I understand and successfully use it?"

### 3. Required Human Personas

Where applicable test from several user perspectives:

- **NEW USER**: Has never used the application
- **ORDINARY USER**: Uses normal functions and expects predictable behaviour
- **POWER USER / PROFESSIONAL**: Uses advanced features, keyboard shortcuts, complex files
- **ACCESSIBILITY USER**: Keyboard-only use, focus order, screen-reader semantics, zoom/scaling, contrast, font scaling, reduced motion, captions/transcripts
- **LOW-RESOURCE USER**: Test on realistic constrained settings

### 4. Human UI Review

For every screen inspect:
- Visual hierarchy, layout, alignment, spacing, typography
- Labels, icons, consistency, discoverability
- Button placement, menus, context menus, toolbars, status bars, sidebars
- Dialogs, modal behaviour, notifications, progress indicators
- Loading states, empty states, error states, success states
- Confirmation states, disabled states, hover/focus states
- Resize behaviour, window minimum size, high DPI/scaling
- Keyboard focus, tab order

Look for:
- Clipping, overlapping controls, tiny text
- Unexplained icons, broken alignment, dead space
- Inconsistent naming, confusing navigation
- Duplicate controls, missing feedback
- Excessive dialogs, hidden important actions
- Unexpected behaviour

### 5. Human UX Review

Evaluate complete workflows. Ask:
- Is the next action obvious?
- Is terminology understandable?
- Are common tasks fast?
- Does the app remember sensible state?
- Does Back behave correctly?
- Can mistakes be undone?
- Can destructive actions be cancelled?
- Are warnings useful rather than annoying?
- Can a beginner succeed?
- Can an expert work efficiently?
- Are advanced controls discoverable without overwhelming beginners?
- Are shortcuts available?
- Are menus logically grouped?
- Does the application behave consistently with the rest of Aetherius?
- Does it feel like one integrated ecosystem rather than unrelated programs?

### 6. Complete Application Life-Cycle Test

Where applicable every substantial app must pass:
INSTALL → FIRST LAUNCH → ONBOARDING → NORMAL LAUNCH → OPEN → CREATE → EDIT → SAVE → SAVE AS → CLOSE → REOPEN → PERSIST STATE → UNDO → REDO → IMPORT → EXPORT → SEARCH → SETTINGS → PERMISSIONS → OFFLINE USE → NETWORK RECONNECT → CRASH RECOVERY → AUTOSAVE/RECOVERY → UPDATE/MIGRATION → UNINSTALL → REINSTALL → OPEN PREVIOUS DATA → OWNER-TESTABLE

Skip a step only when genuinely irrelevant to that application. Record N/A explicitly rather than silently omitting it.

### 7. Test Every Feature, Not Only the Happy Path

Create a feature inventory for each application. For each feature:
- FEATURE_ID
- SCREEN/WORKSPACE
- ENTRY_POINT
- PRECONDITIONS
- TEST_DATA
- EXPECTED_RESULT
- ACTUAL_RESULT
- PASS/FAIL/PARTIAL
- UX_RESULT
- ACCESSIBILITY_RESULT
- PERFORMANCE_RESULT
- ERROR_HANDLING_RESULT
- EVIDENCE
- DEFECT_ID
- RETEST_RESULT

Test: normal use, boundary values, invalid input, empty input, large input, cancel, undo, redo, repeated operation, rapid operation, missing files, corrupt files where safe, permission denied, disk/path issues, offline state, network interruption, service unavailable, dependency unavailable, restart, crash/recovery.

### 8. Do Not Trust UI-Only Implementations

Search all applications/projects for: UI ONLY, MOCK, PLACEHOLDER, NOT CONNECTED, SIMULATED, STUB, TODO, FIXME, PARTIAL, MISSING, NOT IMPLEMENTED, PROTOTYPE, UNVERIFIED.

For every visible UI control determine:
UI CONTROL → HANDLER → SERVICE/ENGINE → PERSISTENCE / ACTION → RESULT → USER FEEDBACK → TEST → HUMAN VERIFICATION

### 9. Performance From the User's Perspective

Measure technical performance AND perceived performance. Record:
- Cold startup, warm startup, time to usable UI
- File-open time, file-save time, search response
- Menu responsiveness, typing/input latency, scrolling
- Rendering smoothness, CPU, RAM, GPU, disk use
- Background processes, idle usage, network use
- Battery impact, large-project behaviour

Look for: frozen UI, blocking operations, unexplained waiting, spinner with no progress, delayed clicks, excessive startup work, memory growth, long shutdown.

### 10. Stability / Recovery

Deliberately test safe failure scenarios. Where applicable:
- Force-close application, reopen, restore autosaved work
- Recover session, missing dependency, malformed user input
- Failed network request, disconnected device
- Unavailable model, unavailable service
- Invalid configuration, interrupted save
- Stale lock, plugin crash, background worker failure

Verify that one failed component does not destroy unrelated user work.

### 11. Human Security / Privacy Experience

Security must also make sense to a normal user. Verify:
- Permissions are understandable
- Requests appear when needed
- Apps request only necessary access
- Denial does not unnecessarily break unrelated features
- Permission revocation works
- Privacy settings are discoverable
- Sensitive information is not exposed in ordinary logs/UI
- User understands when Genesis/agents access files/devices/network
- Background behaviour is visible where appropriate

### 12. Human Agent / Genesis Experience

Where Genesis or another agent appears in an application, test it like a person. Verify:
- Can user find it?
- Can user hide it?
- Can user restore it?
- Does state persist appropriately?
- Does it obstruct normal work?
- Does it understand current application context?
- Are proposed actions distinguishable from completed actions?
- Is user clearly informed before meaningful external/destructive actions?
- Does cancellation work?
- Does agent output link to the action/result?
- Can the user undo/recover?
- Does model/provider failure degrade gracefully?

Maintain Genesis avatar/display modes: HIDDEN, SMALL, STANDARD, FULL_SCREEN.

### 13. Human Testing of Agent Bridge

Agent Bridge must itself be tested through realistic workflows. Examples:
- "open application"
- "open project"
- "read file"
- "edit file"
- "run build"
- "run test"
- "inspect error"
- "repair issue"
- "re-run"
- "save"
- "resume task after restart"

Verify: intent → planning → tool choice → permission → execution → observation → validation → adaptation → persistence → continuation.

Test failures as well as successful executions.

### 14. Human Testing of Aetherius IDE

Because Aetherius IDE now reportedly has a full UI launch path, give it an actual human acceptance audit. Do not merely rerun its existing automated tests.

Launch it normally. Test at minimum:
- Startup, first-run state, workspace/project opening
- File explorer, creating files, editing, saving
- Unsaved-change warning, tabs, search, replace
- Terminal, commands, build, run, tests
- Diagnostics, error navigation, Git
- Settings, themes if present
- Model selection, Agent Bridge integration
- Genesis integration, TaskCenter, ModelCenter
- Restart/persistence, invalid project, missing toolchain
- Interrupted command, large workspace, UI resizing, keyboard navigation

Record every dead control and unfinished workflow. Fix defects. Relaunch. Retest. Repeat until runtime-verified.

### 15. Aetherius OS Requires a Real App Ecosystem

Aetherius OS must ultimately contain a coherent first-party application ecosystem rather than an OS shell with a handful of demonstrations.

Application families:
- CORE / SYSTEM (Files, Search, Settings, Control Centre, App Store, Terminal, etc.)
- PERSONAL / DEFAULT (Calculator, Clock, Calendar, Weather, Maps, etc.)
- OFFICE / PRODUCTIVITY (Documents, Sheets, Presentations, Database, etc.)
- COMMUNICATION (Chat, Meet, Mail, Communities, Remote Assistance)
- CREATIVE (Image, Paint, Vector, Photo, Publishing, Video, VFX, Animation, 3D, Poietek)
- ENGINEERING (CAD, CAM, BIM, Electronics, PCB, etc.)
- SCIENCE (MAT, scientific notebooks, analysis, statistics, etc.)
- DEVELOPER (Aetherius IDE, Git, Terminal, API tools, etc.)

Classify applications appropriately as:
- CORE_SYSTEM
- DEFAULT_INSTALLED
- OPTIONAL_FIRST_PARTY
- APP_STORE
- PROFESSIONAL_OPTIONAL
- BUSINESS_OPTIONAL
- ENTERPRISE_OPTIONAL
- DEVELOPER_OPTIONAL
- SPECIALIST_OPTIONAL
- PLUGIN
- EXTENSION
- SERVICE
- BACKGROUND_COMPONENT

### 16-44. Additional Requirements

See full owner requirement in prompt7.txt for complete details on:
- Reuse all six saved workstreams
- Competitor research must inform human testing
- Quality dashboard
- Five-star target
- New human-validation status
- Defect loop
- Screen-by-screen / workspace-by-workspace audit
- End-to-end user journeys
- Cross-app testing
- File compatibility testing
- Cross-platform testing
- Responsive / device-class UX
- Do not build 1,040 apps
- Continue the 1,040-gap comparison
- Parallel human validation lane
- What to do with non-GUI projects
- Screenshot / visual evidence
- Test data must be realistic
- First-party app ecosystem build policy
- Repository policy
- Research / external technology
- Poietek
- Simulation / scientific software
- Application completeness definition
- Autonomous loop remains active
- Failure logic
- Checkpoints
- Immediate execution order
- Next report format

## Status Chain

DISCOVERED → RESEARCHED → EVALUATED → SELECTED → PLANNED → REPOSITORY_CREATED → IMPLEMENTED → AUTOMATED_TESTED → INTEGRATION_VERIFIED → RUNTIME_VERIFIED → HUMAN_UI_VERIFIED → HUMAN_UX_VERIFIED → HUMAN_WORKFLOW_VERIFIED → HUMAN_FAILURE_RECOVERY_VERIFIED → OWNER_TESTABLE → OWNER_ACCEPTED

Jonathan alone marks: `OWNER_ACCEPTED`

## Autonomous Loop

For every task:
UNDERSTAND → OBSERVE → RETRIEVE CONTEXT → PLAN → SELECT TOOL/MODEL → BUILD → MEASURE → AUTOMATED TEST → LAUNCH → HUMAN TEST → VERIFY → CRITIQUE → DIAGNOSE → ADAPT → RECORD → SELECT NEXT UNBLOCKED TASK → CONTINUE

**LAUNCH → HUMAN TEST** is now a mandatory stage for user-facing software.

## Failure Logic

FAIL → CAPTURE → DIAGNOSE → CHANGE APPROACH → FIX → RETEST AUTOMATICALLY → RELAUNCH → HUMAN RETEST → VERIFY

## Checkpoints

Persist:
- Active app
- Active user journey
- Screen/workspace reached
- Actions executed
- Defects found
- Defects fixed
- Tests run
- Human tests run
- Screens remaining
- Next action

If OpenCode/model/computer restarts: resume from this state. A checkpoint does NOT mean stop.