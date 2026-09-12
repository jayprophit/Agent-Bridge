"""Two-process localhost test harness server (v0.7, synthetic only).

Runs a real NodeServerState over real loopback HTTP in a separate process.
Never touches MAT/Genesis; only serves disposable fixture tasks.

Usage:
    python tests/node_test_server.py --node-id NAME --trust '{"a":"TRUSTED_NODE"}'
        [--tools a,b] [--models m] [--mem MB] [--vram MB] [--gpu 0|1]
        [--executor inspect_project|slow|deny] [--emergency-stop]
        [--revoke node-id ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse_args(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--node-id", required=True)
    p.add_argument("--trust", default="{}")
    p.add_argument("--tools", default="")
    p.add_argument("--models", default="")
    p.add_argument("--mem", type=int, default=8192)
    p.add_argument("--vram", type=int, default=0)
    p.add_argument("--gpu", type=int, default=0)
    p.add_argument("--executor", default="inspect_project",
                   choices=["inspect_project", "slow", "deny", "verbose"])
    p.add_argument("--emergency-stop", action="store_true")
    p.add_argument("--revoke", nargs="*", default=[])
    p.add_argument("--tls-cert", default="")
    p.add_argument("--tls-key", default="")
    p.add_argument("--remote-owner-policy", default="REMOTE_OWNER_DISABLED")
    p.add_argument("--remote-owner-grant", nargs="*", default=[])
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    from nodes.node_server import NodeServerState, serve_node

    trust_map = json.loads(args.trust or "{}")
    revoked = set(args.revoke or [])
    tools = [t for t in args.tools.split(",") if t]
    models = [m for m in args.models.split(",") if m]

    def descriptor():
        return {
            "node_id": args.node_id,
            "device_class": "desktop",
            "platform": "windows",
            "architecture": "x86_64",
            "online": True,
            "tools": tools,
            "models": models,
            "memory_mb": args.mem,
            "gpu_memory_mb": args.vram,
            "gpu_available": bool(args.gpu),
            "filesystem_write": "filesystem.write" in tools,
            "browser_available": False,
            "capabilities": ["coding", "tools"],
        }

    def trust_fn(remote_node_id: str) -> str:
        if remote_node_id in revoked:
            return "REVOKED"
        return trust_map.get(remote_node_id, "UNTRUSTED_NODE")

    def executor(body, context):
        required = list(body.get("required_tools", []))
        allowed = set(tools)
        denied = [t for t in required if t not in allowed]
        if denied:
            raise PermissionError("TOOL_DENIED")
        if args.executor == "deny":
            raise PermissionError("TOOL_DENIED")
        if args.executor == "slow":
            time.sleep(5)
            return {"status": "COMPLETED", "result_summary": "slow fixture done",
                    "tools_used": required, "artifact_references": []}
        if args.executor == "verbose":
            return {"status": "COMPLETED", "result_summary": "V" * 5000,
                    "tools_used": required, "artifact_references": []}
        # inspect_project fixture: synthetic validation state only
        trust = context.get("trust_level", "")
        return {
            "status": "COMPLETED",
            "result_summary": "validation: 3 checks passed, 0 failed (synthetic)",
            "tools_used": required,
            "artifact_references": [{
                "ref": "artifact:validation-state:synthetic-001",
                "hash": "sha256:" + "0" * 64,
                "size": 128,
                "origin_node": args.node_id,
                "verified": trust in ("OWNER_NODE", "TRUSTED_NODE"),
            }],
            "verification": {"verified": trust in ("OWNER_NODE", "TRUSTED_NODE"),
                             "method": "trust-gated-fixture"},
        }

    state = NodeServerState(args.node_id, descriptor, trust_fn, executor)
    if args.emergency_stop:
        state.emergency_stop = True
        state.emergency_reason = "harness emergency stop active"
    state.remote_owner_policy = args.remote_owner_policy
    for scope in args.remote_owner_grant or []:
        state.remote_owner_grants[scope] = True
    tls_config = None
    if args.tls_cert or args.tls_key:
        from nodes.node_transport import TlsConfig
        tls_config = TlsConfig(certfile=args.tls_cert, keyfile=args.tls_key)
    srv = serve_node(state, host="127.0.0.1", port=0, tls_config=tls_config)
    print(f"PORT={srv.server_address[1]}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
