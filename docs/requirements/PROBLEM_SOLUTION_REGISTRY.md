# Canonical Problem/Solution Registry — 450 requirements, 100% traceable

| Domain | Input | Mapped | Unmapped | Duplicate IDs | Coverage |
|---|---|---|---|---|---|
| AI / agent systems | 150 | 150 | 0 | 0 | 100% |
| Cross-device / consumer compute | 150 | 150 | 0 | 0 | 100% |
| Physical (robotics/IoT/embedded/OT/…) | 150 | 150 | 0 | 0 | 100% |
| **TOTAL** | **450** | **450** | **0** | **0** | **100%** |

IDs are permanent (AI-001..150, DEV-001..150, PHY-001..150); never renumber
by severity. A requirement may map to MULTIPLE root systems; shared
solutions never collapse individual IDs.

## Root-system counts

- AI: 19 systems (OutputVerifier … StreamWorkspaceSeparator).
- Device: 18 systems (15 named + ComputePlacementEngine/DataLocalityManager/NodeRouter).
- Physical: 14 systems (12 named + LatencyBudgetManager/IncidentManager).

## Status honesty

SOLVED_V08 only where tests/measured evidence prove it; PARTIAL_V08 where
governors mitigate; ARCHITECTURE_READY for designed-not-built;
PROVIDER_DEPENDENT / EXTERNAL_PLATFORM where others own it;
FUTURE_* / GENESIS_LAYER where scoped; NOT_STARTED only after triage
(none currently untriaged).

## Physical taxonomy (extension labels)

ROBOTICS, IoT, EMBEDDED SYSTEMS, CYBER-PHYSICAL SYSTEMS, OT, ICS, PLC
SYSTEMS, SCADA, MES, DIGITAL FABRICATION, SMART MANUFACTURING, EDGE
CONTROL, AUTOMATION, MACHINE CONTROL, SENSOR NETWORKS, ACTUATOR NETWORKS,
ROS / ROS 2, MICROCONTROLLERS, INDUSTRIAL NETWORKS — domain labels on
PHY entries (see SCOPES_TAXONOMY.md), not separate implementations.

## Safety separation (recorded rule)

GENESIS/AGENT → INTENT → SCOPES TASK ORCHESTRATOR → PLANNER → SAFETY
SUPERVISOR → REALTIME CONTROL → DRIVER/PLC/CONTROLLER → HARDWARE.
AI never issues unsafe raw physical control.
