"""Local Agent Bridge v0.3 configuration.

Precedence (lowest -> highest):
  1. built-in defaults
  2. JSON config file (--config / BRIDGE_CONFIG, e.g. bridge_config.json)
  3. environment variables
  4. CLI arguments

v0.3 adds: per-role models, max_revision_cycles, dry_run, test profile,
context budget, session/task identity. Same-model-for-all-roles is fully
supported (important for low-resource machines).
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "hhao/qwen2.5-coder-tools:3b"
DEFAULT_MODE = "build"
VALID_MODES = ("build", "plan", "hybrid")
VALID_APPROVALS = ("AUTO_SAFE", "ASK_RISKY", "ASK_ALL_WRITES", "READ_ONLY",
                   "OWNER_AUTO_APPROVE")
OWNER_PROFILES = ("OWNER_FULL_ACCESS",)
DEFAULT_APPROVAL = "AUTO_SAFE"
VALID_ROLES = ("planner", "coder", "reviewer", "general")
VALID_REVIEW_AUTHORITY = ("ADVISORY", "EVIDENCE_GATED", "AUTHORITATIVE")
DEFAULT_REVIEW_AUTHORITY = "EVIDENCE_GATED"
VALID_COLLISIONS = ("REFUSE", "REQUIRE_APPROVAL", "OVERWRITE", "CREATE_BACKUP")
DEFAULT_COLLISION = "REQUIRE_APPROVAL"
VALID_PROMPT_PROFILES = ("standard", "small", "strong")
# Role model presets: LOW_RESOURCE shares one model; BALANCED/HIGH_QUALITY
# allow stronger reviewer/planner. No downloads, local models only.
PRESETS = ("LOW_RESOURCE", "STANDARD", "HIGH_QUALITY", "CUSTOM")


@dataclass
class RoleModels:
    planner: str = ""
    coder: str = ""
    reviewer: str = ""
    general: str = ""

    def for_role(self, role: str, default: str) -> str:
        return getattr(self, role, "") or default


@dataclass
class GitSettings:
    enabled: bool = True
    auto_commit: bool = False
    checkpoint_label_prefix: str = "bridge-v06"


@dataclass
class CacheSettings:
    enabled: bool = True
    max_entries: int = 256


@dataclass
class LoggingSettings:
    human_log: str = ""
    jsonl_log: str = ""
    redact_secrets: bool = True


@dataclass
class TestProfileSettings:
    profile: str = "python"  # python | node | generic


@dataclass
class ContextSettings:
    budget_chars: int = 12000
    keep_recent_results: int = 6


@dataclass
class BridgeConfig:
    ollama_url: str = DEFAULT_OLLAMA_URL
    model: str = DEFAULT_MODEL
    workspace: Path = field(default_factory=Path.cwd)
    mode: str = DEFAULT_MODE
    approval: str = DEFAULT_APPROVAL
    max_steps: int = 16
    max_revision_cycles: int = 2
    request_timeout_s: int = 120
    shell_timeout_s: int = 60
    shell_profile: str = "dev"
    non_interactive: bool = True
    dry_run: bool = False
    repeat_threshold: int = 3
    large_write_bytes: int = 102_400
    enable_reviewer: bool = True
    review_authority: str = DEFAULT_REVIEW_AUTHORITY
    # v0.6 owner mode: BOTH required, never inferred from ambiguity
    profile: str = ""
    owner_authorized: bool = False
    network_policy: str = "LOCAL_MODEL_NETWORK"  # or EXTERNAL_NETWORK (owner)
    collision: str = DEFAULT_COLLISION
    prompt_profile: str = "standard"
    preset: str = "LOW_RESOURCE"
    fallback: dict = field(default_factory=dict)  # role -> [models...]
    git: GitSettings = field(default_factory=GitSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    roles: RoleModels = field(default_factory=RoleModels)
    test_profile: TestProfileSettings = field(default_factory=TestProfileSettings)
    context: ContextSettings = field(default_factory=ContextSettings)
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    # v0.8.1 evidence-aware completion: when non-empty, a finish action is
    # VERIFIED_COMPLETE only if every listed workspace-relative artifact
    # exists (and parses when verify_json=True for .json); otherwise the
    # run ends MODEL_CLAIMED_COMPLETE (never falsified success).
    # verify_command (e.g. "python -m unittest") runs through the executor
    # test action and must exit 0 for VERIFIED_COMPLETE.
    expected_artifacts: list = field(default_factory=list)
    verify_json: bool = True
    verify_command: str = ""

    def __post_init__(self) -> None:
        self.ollama_url = self.ollama_url.rstrip("/")
        # owner profile application (explicit only; single source of truth)
        if self.profile == "OWNER_FULL_ACCESS":
            self.approval = "OWNER_AUTO_APPROVE"
            self.shell_profile = "owner"
            if self.network_policy == "LOCAL_MODEL_NETWORK":
                self.network_policy = "EXTERNAL_NETWORK"
        if self.mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}")
        if self.approval not in VALID_APPROVALS:
            raise ValueError(f"approval must be one of {VALID_APPROVALS}")
        if self.collision not in VALID_COLLISIONS:
            raise ValueError(f"collision must be one of {VALID_COLLISIONS}")
        if self.prompt_profile not in VALID_PROMPT_PROFILES:
            raise ValueError(f"prompt_profile must be one of {VALID_PROMPT_PROFILES}")
        if self.preset not in PRESETS:
            raise ValueError(f"preset must be one of {PRESETS}")
        if self.review_authority not in VALID_REVIEW_AUTHORITY:
            raise ValueError(f"review_authority must be one of {VALID_REVIEW_AUTHORITY}")
        if self.profile and self.profile not in OWNER_PROFILES + (
                "SAFE_EXPLORATION", "ASSISTED_BUILD", "AUTONOMOUS_SANDBOX",
                "PRECIOUS_PROJECT"):
            raise ValueError(f"unknown profile {self.profile!r}")
        if self.profile == "OWNER_FULL_ACCESS" and not self.owner_authorized:
            raise ValueError("OWNER_FULL_ACCESS requires owner_authorized=true "
                             "(explicit --owner-authorized)")
        if self.network_policy not in ("LOCAL_MODEL_NETWORK", "EXTERNAL_NETWORK",
                                       "NO_NETWORK"):
            raise ValueError("unknown network_policy")
        ws = Path(self.workspace).expanduser().resolve()
        if not ws.exists():
            raise ValueError(f"workspace does not exist: {ws}")
        if not ws.is_dir():
            raise ValueError(f"workspace is not a directory: {ws}")
        self.workspace = ws

    def model_for(self, role: str) -> str:
        if role not in VALID_ROLES:
            role = "general"
        return self.roles.for_role(role, self.model)


def _from_json_file(path: str | Path) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"config file not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config file must contain a JSON object")
    return data


def _apply_dict(cfg: BridgeConfig, d: dict) -> BridgeConfig:
    g = dict(d)
    if "ollama_host" in g and "ollama_url" not in g:
        g["ollama_url"] = g.pop("ollama_host")
    # {"models": {role: name}} alias for roles
    if isinstance(g.get("models"), dict):
        g["roles"] = g.pop("models")
    for k in ("ollama_url", "model", "workspace", "mode", "approval",
              "max_steps", "max_revision_cycles", "request_timeout_s",
              "shell_timeout_s", "shell_profile", "non_interactive", "dry_run",
              "repeat_threshold", "large_write_bytes", "enable_reviewer",
              "review_authority", "profile", "owner_authorized",
              "network_policy",
              "collision", "prompt_profile", "preset"):
        if k in g and g[k] not in ("", None):
            setattr(cfg, k, Path(g[k]) if k == "workspace" else g[k])
    if isinstance(g.get("fallback"), dict):
        cfg.fallback = {str(k): list(v) for k, v in g["fallback"].items()}
    for section, cls in (("git", GitSettings), ("cache", CacheSettings),
                         ("logging", LoggingSettings),
                         ("roles", RoleModels),
                         ("test_profile", TestProfileSettings),
                         ("context", ContextSettings)):
        if isinstance(g.get(section), dict):
            target = getattr(cfg, section)
            for sk, sv in g[section].items():
                if hasattr(target, sk):
                    setattr(target, sk, sv)
    cfg.__post_init__()
    return cfg


def _apply_env(cfg: BridgeConfig) -> BridgeConfig:
    e = os.environ
    if e.get("OLLAMA_HOST") or e.get("OLLAMA_URL"):
        cfg.ollama_url = (e.get("OLLAMA_URL") or e["OLLAMA_HOST"]).rstrip("/")
    for var, attr, cast in (
        ("BRIDGE_MODEL", "model", str), ("BRIDGE_WORKSPACE", "workspace", Path),
        ("BRIDGE_MODE", "mode", str), ("BRIDGE_APPROVAL", "approval", str),
        ("BRIDGE_MAX_STEPS", "max_steps", int),
        ("BRIDGE_MAX_REVISIONS", "max_revision_cycles", int),
        ("BRIDGE_REQUEST_TIMEOUT", "request_timeout_s", int),
        ("BRIDGE_SHELL_TIMEOUT", "shell_timeout_s", int),
        ("BRIDGE_SHELL_PROFILE", "shell_profile", str),
        ("BRIDGE_TEST_PROFILE", None, None),
        ("BRIDGE_PROFILE", "profile", str),
        ("BRIDGE_NETWORK", "network_policy", str),
        ("BRIDGE_REVIEW_AUTHORITY", "review_authority", str),
    ):
        if e.get(var):
            if var == "BRIDGE_TEST_PROFILE":
                cfg.test_profile.profile = e[var]
            else:
                setattr(cfg, attr, cast(e[var]))
    if e.get("BRIDGE_LOG"):
        cfg.logging.human_log = e["BRIDGE_LOG"]
    if e.get("BRIDGE_JSONL"):
        cfg.logging.jsonl_log = e["BRIDGE_JSONL"]
    if e.get("BRIDGE_NON_INTERACTIVE"):
        cfg.non_interactive = e["BRIDGE_NON_INTERACTIVE"].lower() not in ("0", "false", "no")
    if e.get("BRIDGE_DRY_RUN"):
        cfg.dry_run = e["BRIDGE_DRY_RUN"].lower() in ("1", "true", "yes")
    if e.get("BRIDGE_OWNER_AUTHORIZED"):
        cfg.owner_authorized = e["BRIDGE_OWNER_AUTHORIZED"].lower() in ("1", "true", "yes")
    for role in VALID_ROLES:
        var = f"BRIDGE_MODEL_{role.upper()}"
        if e.get(var):
            setattr(cfg.roles, role, e[var])
    return cfg


def config_from_args(argv: list[str] | None = None) -> tuple[BridgeConfig, str]:
    p = argparse.ArgumentParser(description="Local Agent Bridge v0.3")
    p.add_argument("--config", default=os.environ.get("BRIDGE_CONFIG", ""))
    p.add_argument("--host", default="")
    p.add_argument("--model", default="")
    p.add_argument("--planner-model", default="")
    p.add_argument("--coder-model", default="")
    p.add_argument("--reviewer-model", default="")
    p.add_argument("--general-model", default="")
    p.add_argument("--workspace", default="")
    p.add_argument("--mode", default="", choices=list(VALID_MODES) + [""])
    p.add_argument("--approval", default="", choices=list(VALID_APPROVALS) + [""])
    p.add_argument("--max-steps", type=int, default=0)
    p.add_argument("--max-revisions", type=int, default=-1)
    p.add_argument("--request-timeout", type=int, default=0)
    p.add_argument("--shell-timeout", type=int, default=0)
    p.add_argument("--shell-profile", default="",
                   choices=["", "strict", "dev", "owner"])
    p.add_argument("--test-profile", default="", choices=["", "python", "node", "generic"])
    p.add_argument("--collision", default="",
                   choices=["", "REFUSE", "REQUIRE_APPROVAL", "OVERWRITE", "CREATE_BACKUP"])
    p.add_argument("--prompt-profile", default="",
                   choices=["", "standard", "small", "strong"])
    p.add_argument("--preset", default="",
                   choices=["", "LOW_RESOURCE", "STANDARD", "HIGH_QUALITY", "CUSTOM"])
    p.add_argument("--log", default="")
    p.add_argument("--jsonl", default="")
    p.add_argument("--no-reviewer", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="inspect/plan/validate only; NEVER mutate or execute")
    p.add_argument("--task", default="")
    p.add_argument("--task-file", default="")
    p.add_argument("--interactive", action="store_true")
    p.add_argument("--profile", default="",
                   choices=["", "SAFE_EXPLORATION", "ASSISTED_BUILD",
                            "AUTONOMOUS_SANDBOX", "PRECIOUS_PROJECT",
                            "OWNER_FULL_ACCESS"])
    p.add_argument("--owner-authorized", action="store_true",
                   help="explicit machine-owner authorization (with --profile OWNER_FULL_ACCESS)")
    p.add_argument("--network", default="",
                   choices=["", "LOCAL_MODEL_NETWORK", "EXTERNAL_NETWORK",
                            "NO_NETWORK"])
    p.add_argument("--review-authority", default="",
                   choices=["", "ADVISORY", "EVIDENCE_GATED", "AUTHORITATIVE"])
    p.add_argument("--milestones", default="",
                   help="comma-separated required milestones for FINISH acceptance")
    p.add_argument("--replay", default="", help="JSONL session file to audit/verify")
    p.add_argument("--replay-mode", default="audit",
                   choices=["audit", "verify", "rerun_safe"])
    a = p.parse_args(argv)

    cfg = BridgeConfig(workspace=Path.cwd())
    if a.config:
        _apply_dict(cfg, _from_json_file(a.config))
    _apply_env(cfg)
    if a.host:
        cfg.ollama_url = a.host.rstrip("/")
    if a.model:
        cfg.model = a.model
    if a.workspace:
        cfg.workspace = Path(a.workspace)
    if a.mode:
        cfg.mode = a.mode
    if a.approval:
        cfg.approval = a.approval
    if a.max_steps:
        cfg.max_steps = a.max_steps
    if a.max_revisions >= 0:
        cfg.max_revision_cycles = a.max_revisions
    if a.request_timeout:
        cfg.request_timeout_s = a.request_timeout
    if a.shell_timeout:
        cfg.shell_timeout_s = a.shell_timeout
    if a.shell_profile:
        cfg.shell_profile = a.shell_profile
    if a.test_profile:
        cfg.test_profile.profile = a.test_profile
    if a.collision:
        cfg.collision = a.collision
    if a.prompt_profile:
        cfg.prompt_profile = a.prompt_profile
    if a.preset:
        cfg.preset = a.preset
    if a.log:
        cfg.logging.human_log = a.log
    if a.jsonl:
        cfg.logging.jsonl_log = a.jsonl
    if a.no_reviewer:
        cfg.enable_reviewer = False
    if a.dry_run:
        cfg.dry_run = True
    if a.interactive:
        cfg.non_interactive = False
    if a.planner_model:
        cfg.roles.planner = a.planner_model
    if a.coder_model:
        cfg.roles.coder = a.coder_model
    if a.reviewer_model:
        cfg.roles.reviewer = a.reviewer_model
    if a.general_model:
        cfg.roles.general = a.general_model
    if a.profile:
        cfg.profile = a.profile
    if a.owner_authorized:
        cfg.owner_authorized = True
    if a.network:
        cfg.network_policy = a.network
    if a.review_authority:
        cfg.review_authority = a.review_authority
    # owner profile application happens in __post_init__ (explicit only)
    cfg.__post_init__()
    milestones = [m.strip() for m in (a.milestones or "").split(",") if m.strip()]

    task = a.task
    if a.task_file:
        task = Path(a.task_file).read_text(encoding="utf-8")
    if not task and not a.replay:
        p.error("provide --task '...' or --task-file <file> (or --replay <file>)")
    return cfg, task, milestones


def to_dict(cfg: BridgeConfig) -> dict:
    d = asdict(cfg)
    d["workspace"] = str(cfg.workspace)
    return d
