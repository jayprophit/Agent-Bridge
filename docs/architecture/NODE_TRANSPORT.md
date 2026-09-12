# Node Transport (v0.7)

## Implemented transports

| Transport | Status | Notes |
|---|---|---|
| IN_MEMORY | IMPLEMENTED_VERIFIED | Legacy `nodes.task_delegator.NodeTransport`; deterministic unit tests |
| HTTP (loopback) | IMPLEMENTED_VERIFIED | `nodes.node_transport.HttpNodeTransport` + `nodes.node_server.serve_node`; stdlib only; two-process localhost tests green |
| HTTPS | CONFIGURATION_REQUIRED | `TlsConfig` (stdlib `ssl`, TLS 1.2 minimum); no certs shipped, so HTTPS reports `CONFIGURATION_REQUIRED`, never fake AVAILABLE |
| SSE / HTTP streaming | IMPLEMENTED_VERIFIED | Delegation events endpoint streams `text/event-stream`; client polls `.../events` |
| WEBSOCKET | NOT_INSTALLED / INTERFACE_ONLY | No websocket backend installed; nothing was installed for this increment |

## Plaintext safety

- Default bind is `127.0.0.1`. `serve_node()` refuses `0.0.0.0` unless explicitly approved.
- `HttpNodeTransport` refuses plain HTTP to non-loopback hosts with
  `REMOTE_PLAINTEXT_DENIED` unless `allow_insecure_dev=True` (default OFF).
- Remote plaintext never carries task content: the check runs before serialization.

## Endpoints (all JSON, size-capped, no arbitrary execution)

- `GET /v1/node/health`, `/v1/node/descriptor`, `/v1/node/protocol`
- `POST /v1/node/handshake` (version negotiation)
- `POST /v1/node/pairing/request|approve|challenge`
- `POST /v1/node/delegations`, `GET /v1/node/delegations/{id}`,
  `GET /v1/node/delegations/{id}/events` (SSE),
  `POST /v1/node/delegations/{id}/cancel`
- `GET /v1/node/artifacts/{ref}` (metadata only, never file bodies)
- `POST /v1/node/heartbeat`, `POST /v1/node/capabilities/refresh`

Remote execution always flows through target-side revalidation
(trust → pairing → privacy → capabilities → emergency stop → tool
authorization) before the injected executor runs.
