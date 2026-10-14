#!/usr/bin/env python
"""External API key loader (§20 ADOPT_NOW = action).

The five cloud providers (OpenRouter, Gemini, Groq, HuggingFace, DeepSeek)
are BLOCKED_OWNER because the previous keys were exposed. The owner supplies
fresh keys in ONE of two places, and this module makes them activate with
ZERO code changes:

  1. `.env.local` in the repo root (gitignored — line 229 of .gitignore):
         CRED-OPENROUTER-PRIMARY=sk-or-...
         CRED-GEMINI-PRIMARY=AIza...
         ...
  2. KeePass entries titled exactly `CRED-<PROVIDER>-PRIMARY` (the
     credential broker's order — it already checks env first, vault second).

Resolution order: .env.local → process environment → vault (broker). The
first source that yields a non-empty value wins. A provider with no key
resolves to None and its adapter stays dormant — the programme NEVER blocks
on a missing key (§35: block only the action that genuinely needs it).

Usage:
    from compute.credential_loader import load_credentials, provider_status

    creds = load_credentials()          # {ref: key} for present keys only
    status = provider_status()          # {provider: LIVE_KEY_PRESENT|AWAITING_KEY}

Secrets rule: this module NEVER logs, prints, or persists key VALUES. Only
presence. Tests assert that.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

# The five refs, in priority order (OpenRouter first — one key, many models).
CREDENTIAL_REFS = (
    "CRED-OPENROUTER-PRIMARY",
    "CRED-GEMINI-PRIMARY",
    "CRED-GROQ-PRIMARY",
    "CRED-HUGGINGFACE-PRIMARY",
    "CRED-DEEPSEEK-PRIMARY",
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_LOCAL = _REPO_ROOT / ".env.local"


def _read_env_local() -> Dict[str, str]:
    """Parse .env.local into {ref: value}. Missing file -> {}.

    Deliberately tiny (no python-dotenv dependency): KEY=VALUE lines, #
    comments, surrounding quotes stripped. A malformed line is skipped, not
    fatal — one typo must not take down the loader.
    """
    if not _ENV_LOCAL.exists():
        return {}
    out: Dict[str, str] = {}
    try:
        for line in _ENV_LOCAL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in CREDENTIAL_REFS and value:
                out[key] = value
    except OSError:
        return {}
    return out


def load_credentials() -> Dict[str, str]:
    """Return {ref: key} for every ref with a value, from any source.

    Sources in order: process environment, then .env.local. (The vault is
    consulted by the broker at call time, not here — this loader covers the
    file/env path the owner asked for.)
    """
    found: Dict[str, str] = {}
    for ref in CREDENTIAL_REFS:
        value = os.environ.get(ref) or _read_env_local().get(ref)
        if value:
            found[ref] = value
    return found


def provider_status() -> Dict[str, str]:
    """{provider: 'LIVE_KEY_PRESENT' | 'AWAITING_KEY'} — presence only.

    This is what the dashboard and the hive scheduler read: a provider with
    a key becomes eligible for model routing; without one it stays dormant
    and local capacity carries the work. NEVER returns key values.
    """
    present = load_credentials()
    return {
        ref.replace("CRED-", "").replace("-PRIMARY", "").lower(): (
            "LIVE_KEY_PRESENT" if ref in present else "AWAITING_KEY"
        )
        for ref in CREDENTIAL_REFS
    }


def missing_refs() -> list[str]:
    """The refs still needing owner-supplied keys (for the ready-queue task)."""
    present = load_credentials()
    return [ref for ref in CREDENTIAL_REFS if ref not in present]
