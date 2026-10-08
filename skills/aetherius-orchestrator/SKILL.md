# Aetherius Orchestrator

You supervise. The orchestrator dispatches. Use this interface instead of
prompting for capabilities you do not natively have (spawning agents,
managing worktrees, selecting free models).

## Install

This skill lives in the Agent-Bridge repo so Hermes core stays untouched.
Reference it from your session; all business logic lives in
`orchestrator.py`, never in this prompt text.

## Concepts

- **Task contract**: objective + role + repo/branch/worktree + allowed
  paths + privacy class + cost policy + acceptance tests + expected
  artifacts + dependencies. Submit it; the orchestrator owns the rest.
- **Workers**: `opencode` (repo implementation), `ollama` (review /
  summarise / classify / analyse), `agent-bridge` (app/tool execution),
  `openclaw` (BLOCKED_OPTIONAL — skipped automatically).
- **Policy**: FREE_FIRST_STRICT is always on. Routine models are
  LOCAL_FREE / CLOUD_ZERO_COST / CLOUD_RECURRING_FREE. Paid-only,
  subscription-only and unknown-cost routes are hidden from unattended
  execution. Local Ollama is the guaranteed fallback. No silent paid
  escalation, ever.

## Commands (run from the Agent-Bridge directory)

Submit a review task:
```bash
python -c "
from orchestrator import Orchestrator, OrchestratorTask
from worker_adapters import OllamaWorkerAdapter
o = Orchestrator('.orchestrator', adapters={'ollama': OllamaWorkerAdapter()})
tid = o.submit(OrchestratorTask(objective='Review the diff for null handling',
    role='reviewer', required_capabilities=['review']))
print(o.dispatch(tid))"
```

Submit a coding task (OpenCode implements; tests verify):
```bash
python -c "
from orchestrator import Orchestrator, OrchestratorTask
from worker_adapters import OpenCodeAdapter
o = Orchestrator('.orchestrator', adapters={'opencode': OpenCodeAdapter()})
tid = o.submit(OrchestratorTask(objective='Fix the parser edge case',
    role='coder', repo='.', allowed_paths=['src/'],
    acceptance_tests=['unit'], expected_artifacts=[]))
print(o.dispatch(tid))"
```

Check status / list ready / retry / cancel: use `o.get(tid)`,
`o.ready()`, `o.dispatch(tid)` again (bounded retries), `o.cancel(tid)`.

## Rules for you (Hermes)

- Never ask Jonathan which worker, which free model, retry, continue,
  or what next when policy determines the answer.
- Ask only for: paid spend, credential entry, destructive operations,
  KYC/legal/account actions, material unresolved architecture decisions,
  true owner blockers.
- A worker's completion claim is never enough: the orchestrator verifies
  (diff inspected, tests run, artifacts present) before COMPLETE.
- Optional blocked workers (OpenClaw) never stall other work.
