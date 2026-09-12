# Task Delegation (v0.7)

`nodes.TaskDelegator` routes via `NodeRouter`, then executes locally or
delegates over a `NodeTransport`. Delegation IDs, timeouts, cancellation,
remote failure, result metadata, and audit are tracked; history is retained.
Results return summaries plus ArtifactRegistry references, never giant
bodies. In-memory transport serves deterministic unit tests; HTTP transport
serves the real loopback harness.
