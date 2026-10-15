# H01: Multi-Tenant Isolation Design (AT-22)

**Maps to:** V2 §14 H01, A03/P03, F04/F06, B04, AT-22
**Status:** DESIGN_ONLY (not yet implemented — design phase)

## 1. Code Inspection Report: Current Isolation Points

### 1.1 Current State (single-owner/private deployment)

The current system is **single-tenant**. No data model carries a tenant ID.
Isolation is achieved through:

| Layer | Mechanism | File | Gap |
|-------|-----------|------|-----|
| Task scope | `project_id` field on `OrchestratorTask` | orchestrator.py:84 | Single string, no access control |
| Privacy | `PRIVACY_PUBLIC` / `PRIVACY_PROJECT` / `PRIVACY_CONFIDENTIAL` | models/inference_contract.py | Not enforced as access boundary |
| Cost | `FREE_ONLY` / `HOBBY_CREDIT_ONLY` budget class | compute/cost_engine.py | Per-worker, not per-user |
| Worker env | `environments: list[str]` (e.g. `["local"]`) | task_dag.py:273 | No network isolation |
| Workspace | "Workspace isolation (§12)" | compute/enterprise_team.py:19 | Within-team only |
| Team | `privacy_policy`, `cost_policy` on TeamRecord | compute/team_registry.py:276-277 | Single-org, no cross-tenant boundary |
| Authority | P25 PolicyEngine grants/roles | aether_policy_bridge.py:301 | Keyed by subject string, no tenant prefix |

### 1.2 What's Missing (Tenant Isolation Gaps)

1. **No tenant ID** in `TeamRecord`, `WorkerCareerRecord`, `InstanceRecord`, `OrchestratorTask`, or `WorkerInfo`
2. **No API-layer tenant scoping** — all queries are global
3. **No database-layer tenant partitioning** — all tables are shared
4. **No cross-tenant access prevention** — a worker from tenant A can read tenant B's tasks
5. **No per-user quota/budget reservations** — only global free-tier limits
6. **No credential scoping** — provider credentials are shared across all users

## 2. Design: Tenant Isolation Boundary

### 2.1 Principal Hierarchy

The system defines five principal classes (V2 H01):

| Principal | Definition | Current State | Design Addition |
|-----------|-----------|---------------|-----------------|
| **Platform Admin** | Aetherius OS operator | No concept exists | `principal.kind = "platform_admin"` |
| **Human User** | The person giving instructions | `principal.kind = "owner"` (aether_policy_bridge.py) | Rename/refine to `"user"` |
| **Genesis Identity** | Persistent AI identity | `principal.kind = "genesis"` | Already exists in PrincipalContext |
| **Team Leader** | Coordinates a team | `WorkerCareerRecord.team_lead_of` | Exists but not principal-scoped |
| **Subagent** | Nested worker | `WorkerInfo.worker_id` | Needs tenant prefix |
| **Service Account** | Non-human programmatic access | Not implemented | New: `principal.kind = "service_account"` |
| **Provider Credential** | API key/secret | CostPolicyEngine grants | Needs per-user scoping |

### 2.2 Tenant Boundary Layers

```
┌─────────────────────────────────────────────────────────┐
│  API GATEWAY                                             │
│  tenant_id = parsed from auth token                      │
│  → All queries prefixed: WHERE tenant_id = X             │
├─────────────────────────────────────────────────────────┤
│  DATABASE / STATE STORE                                  │
│  Rows partitioned by tenant_id (row-level or schema)     │
│  Vector embeddings: namespace = "tenant:<id>:..."        │
├─────────────────────────────────────────────────────────┤
│  MODEL GATEWAY                                           │
│  Provider credentials scoped per user                    │
│  Quota/budget reservations: tenant_id → credits          │
├─────────────────────────────────────────────────────────┤
│  OBJECT STORAGE                                           │
│  Paths prefixed: /tenant/<id>/workspace/<ws>/            │
├─────────────────────────────────────────────────────────┤
│  MESSAGING / CACHE                                       │
│  Channel namespaces: topic.tenant.<id>                   │
│  Cache keys prefixed: cache:tenant:<id>:...               │
├─────────────────────────────────────────────────────────┤
│  BACKUP / EXPORT                                         │
│  Backups tagged with tenant_id                           │
│  Restore scoped to tenant                                │
└─────────────────────────────────────────────────────────┘
```

### 2.3 Data Model Extension (Design Only — Not Implemented)

Add `tenant_id: str = ""` to core dataclasses. The field defaults to empty
string for backward compatibility (single-owner mode). When non-empty, all
queries and storage operations are scoped.

```python
@dataclass
class TeamRecord:
    team_id: str
    tenant_id: str = ""       # NEW: "" = single-owner mode
    ...

@dataclass
class WorkerCareerRecord:
    worker_id: str
    tenant_id: str = ""       # NEW
    ...

@dataclass
class OrchestratorTask:
    task_id: str = ...
    tenant_id: str = ""       # NEW
    ...
```

### 2.4 Per-User Quota/Budget Reservations

Design: `compute/resource_governor.py` already tracks CPU/RAM/GPU. Extend with:
- Per-tenant quota buckets: `tenant_quotas: dict[str, ResourceBudget]`
- Reservation before task start (fail if insufficient)
- Hard limits: no oversubscription across tenants
- Abuse detection: rate-limit task creation per tenant

### 2.5 Cross-Tenant Access Prevention

- **Frontend**: All UI queries include `tenant_id` filter
- **Backend**: Every data access layer method requires `tenant_id` parameter
- **Worker isolation**: A worker from tenant A CANNOT read tenant B's tasks
  even if it guesses the task_id — enforced at the query layer
- **Credential isolation**: Each tenant's provider credentials are stored
  in separate vault paths: `vault://tenant/<id>/providers/<name>/key`

## 3. AT-22: Multi-Tenant Isolation Simulation

The test (`tests/test_at22_multitenant_isolation.py`) verifies:
1. Two synthetic users cannot access each other's tasks by task_id
2. Two synthetic users have separate knowledge/vector stores
3. Two synthetic users have separate file/workspace access
4. Two synthetic users have separate provider quota pools

## 4. Implementation Phasing

- **Phase 1 (current)**: Design only — this document + AT-22 simulation test
- **Phase 2 (future)**: Add `tenant_id` field to data models, default to ""
- **Phase 3 (future)**: Multi-tenant query scoping in all data access layers
- **Phase 4 (future)**: Per-tenant quota/budget and credential isolation

Per V2 H01: "Do not implement full federation yet — design only."
