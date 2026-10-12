# Codex cooldown expiry repair — 2026-10-12

Scope: close the cooldown-expiry defect in `17d71db` on
`unit/external-worker-telemetry`. That baseline was already present on origin;
there were no tracked edits when this continuation began.

The previous parser advanced an elapsed reset to tomorrow on every observation.
It also searched arbitrary rollout text, formatted unknown reset values as
numbers, and left quota data on workers after they resumed.

The parser now selects the latest task lifecycle event, anchors the printed
local reset time to the error timestamp, and expires it once that deadline
passes. Midnight crossings advance relative to the error date, never the
polling date. A later task start or completion supersedes the old error.
Quoted errors in messages are not quota evidence. Missing or invalid reset
times remain unknown and can be displayed without raising an exception.
Running and idle observations clear the old worker quota data.

Compatibility: timestamp-free legacy events use the rollout modification time
as their date anchor. Printed reset clocks are interpreted in the machine's
local timezone, as before. This does not establish quota availability through
a provider API or add support for other error schemas.

Validation: **173 passed in 208.28 seconds**, exit 0, using the existing
`agent-bridge-verify` virtual environment:

```text
python -m pytest tests/test_supervisor_runtime.py tests/test_supervision.py tests/test_hive_scheduler.py tests/test_supervisor_dashboard.py tests/test_supervised_workers.py tests/test_resource_governor.py -q
```

Regression coverage includes exact reset expiry, stale errors on later days,
midnight rollover, superseding lifecycle events, quoted error text, unknown
and invalid reset clocks, and clearing quota data on running/idle workers.
`git diff --check` also passed.

The full repository suite and deployed daemon restart are outside this focused
verification. Existing local runtime state is not committed. The unrelated
`scripts/serve_supervisor_dashboard.py` appeared during this work and belongs
to a concurrent writer; it is excluded from this change.
