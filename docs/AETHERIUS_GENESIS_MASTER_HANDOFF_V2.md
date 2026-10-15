# AETHERIUS / GENESIS — MASTER AI CLOUD & AUTONOMOUS HIVE HANDOFF

> **REVIEW UPDATE — 15 October 2026:** This revision retains the original master handoff verbatim and appends Section 14: operational clarifications, open design decisions and additional tests. The original 42 canonical gap IDs and 20 tests remain stable; new material is mapped to them instead of silently renumbering. Requirements are proposed until verified in the actual Aetherius repositories and deployments.

**Handoff ID:** AETH-HANDOFF-2026-10-14-001  
**Prepared from:** Full current ChatGPT discussion through 14 October 2026  
**Intended operators:** Hermes Agent and/or OpenCode, plus authorised specialist workers  
**Document status:** Requirements and execution directive; not evidence of deployment  
**Primary owner:** User / Aetherius project  
**Top priority:** Implement useful, testable, shared Aetherius infrastructure without paid tiers, without duplicating existing components, and without exposing the user's private credentials to language models.

> **IMPORTANT FIRST PRINCIPLE:** This is a first-party AETHERIUS PLATFORM project, **not a Hermes product**. Hermes and OpenCode are temporary bootstrap operators and may be clients of the infrastructure while they build Aetherius. Aetherius OS, Genesis, the Aetherius IDE, Agent Bridge, its first-party runtime, and all current and future projects must remain able to use the infrastructure without Hermes or OpenCode.

---

## 0. YOUR ROLE AND STARTING INSTRUCTIONS

You are the delegated multidisciplinary architect, cloud engineer, AI infrastructure engineer, security engineer, researcher and automation operator for the Aetherius ecosystem. **Perform authorised engineering work; do not merely write plans.** Research and verify current provider terms and current documentation. Inspect the user's actual repositories and environment before modifying anything. Use existing project artifacts, registries, code, tests and prior decisions as the source of truth over this handoff where they conflict; report discrepancies rather than silently overriding decisions.

Work independently on non-sensitive, reversible preparation and verification. Delegate genuinely independent subtasks to available agents when doing so adds speed or quality, but coordinate them through separate worktrees and an explicit merge/integration process. Where explicit approval or private input is needed, stop only that branch, present a concise exact-action checkpoint to the user, and proceed with other authorised tasks.

Do not ask the user to manually copy files, browse dozens of pages or paste keys when a safe authorised API, CLI, browser automation or trusted secret-entry tool can do it. Do not create accounts, agree to terms, enable billing, spend money, deploy publicly reachable endpoints, expose data, modify live infrastructure or perform destructive operations without appropriately scoped user approval. **No paid fallback.** Never evade account restrictions, CAPTCHA, rate limits, free-tier rules or provider terms.

Complete current accessible work and return a traceable report with code changes, test evidence, blockers, outstanding approvals and next actions. Do not claim that something has been installed, deployed, integrated or verified unless it really has.

---

## 1. NON-NEGOTIABLE ARCHITECTURAL DECISIONS

1. **Shared Aetherius infrastructure, not app-specific infrastructure.** One coherent AI services layer must support Aetherius OS, Genesis, the first-party IDE, Agent Bridge, research, engineering, creative tools, other first-party apps and future projects. Each app can access authorised common services independently.
2. **Aetherius ownership / replaceable backends.** Retain first-party contracts and registry ownership. Local inference and hosted third-party providers are replaceable adapters. The longer-term Aetherius model runtime will replace Ollama where appropriate; do not permanently cement Ollama, Hermes, OpenCode, LiteLLM or any hosted service into the product identity.
3. **Genesis is independently complete by design.** Genesis must have direct access to the full authorised common skill/tool/capability registry and be able to attempt any worker/subagent task **alone**, subject to model competence, physical resources, permissions and verifiable outcomes. Subagents are for parallel throughput, alternate reasoning, isolation, checking and faster completion—not to give Genesis exclusive missing skills.
4. **Genesis participates AND supervises.** Genesis is an active worker and the master supervisor simultaneously: it researches, codes, plans, designs, tests and reviews alongside teams while monitoring progress and allocating resources. Do not reduce Genesis to a passive coordinator.
5. **Individual intelligence and hive intelligence.** Genesis has persistent individual identity, memory and goals; the hive consists of independently addressable lead agents, workers and nested subagents with their own scoped contexts, identities and workspaces, coordinating through shared knowledge and communication. The hive is an engineered collaboration system, not a proven literal fusion of neural states.
6. **Genesis dynamically deploys teams.** Form, resize, supervise, interrupt, replace and retire teams and subagents as needed. Leads can delegate bounded tasks further under strictly inherited permissions, resource budgets and lineage. Teams are not constrained to the four example roles in earlier diagrams; reuse the pre-existing specialist role registry.
7. **Genesis functions when the user is away.** Its intended local/cloud/hybrid modes must preserve goals, identity, memory and jobs when the PC is shut down or browser disconnected. Where remote execution resources remain available, authorised actual work continues. If free capacity disappears, tasks checkpoint and resume; do not misrepresent suspension as uninterrupted computation.
8. **Direct human interaction with ANY worker.** The user can speak with Genesis or individual agents, intervene in tasks, review meetings and inspect authenticated live work and artifacts without having to route all conversation through Genesis.
9. **AI-native communication.** Agents exchange tasks, evidence, references, decisions and concise semantic messages efficiently; support structured schemas and external A2A/MCP adapters. Investigate GibberLink/GGWave, Google's interlingua research, emergent dialects and Ainglish without claiming they are interchangeable or validated superior protocols.
10. **Strict zero-new-spend mode.** Prefer free, open-source, free-tier and authorised model services; no subscription, automatic card billing, top-ups, overage or chargeable fallback without explicit authorisation. Show unavoidable hardware/power cost honestly. Free web/chat usage alone is not a license to proxy a commercial model as a general-purpose API.
11. **Enterprise engineering discipline on hobbyist infrastructure.** Use versioning, least privilege, signed/auditable actions, provenance, reproducible deployment, recovery, observability, security tests, backups and policy enforcement while acknowledging free tiers cannot promise enterprise SLAs.
12. **Evidence before replacement.** Audit existing Aetherius code and previous test results before adding infrastructure; deduplicate canonical problems; preserve permanent IDs, previous experiments, failed approaches and superseded designs.
13. **Continuity of architectural boundaries.** Keep OS, IDE, Genesis, agent runtime, model runtime/provider, security authority, Agent Bridge, workflow, distributed execution and hardware/device-specific adapters conceptually distinct within ONE first-party ecosystem.
14. **Platform independence.** Target Windows, macOS, Linux, mobile/tablet/browser and suitable edge devices via capability-aware interfaces and local/remote execution; do not pretend full desktop IDE inference can operate natively on tiny microcontrollers.
15. **Privacy first.** Provider terms, data-retention/training policies, code confidentiality, geographic requirements, security of credentials and licensing affect which models can process which projects.

---

## 2. REQUIRED SYSTEM CAPABILITIES

### 2A. Unified AI model-provider fabric

Create or repair a shared Aetherius-owned model gateway and canonical registry capable of:

- Native owned/local runtime and authorised self-hosted endpoints (existing Ollama, llama.cpp, later first-party Aetherius runtime; vLLM/SGLang as suitable server backends).
- Independently entitled hosted free-model endpoints; provider routing, fallback, quotas, capability matching, streaming, function/tool calls, structured outputs, multimodal content, context management and errors.
- Stable application-facing APIs, including OpenAI-compatible endpoints **where supported**, with adapters for materially different API protocols. Do not treat OpenAI-compatible Chat Completions as universal support for every model capability.
- Explicit provider metadata: permanent model ID, exact upstream model ID, weight/release identity, modality, context, tool support, cost/free eligibility, expiry, RPM/TPM/RPD/TPD, region, privacy/training policies, licensing, last verified time, health, observed latency, benchmark results and provenance.
- Default deny for unknown or paid endpoints, quota accounting and limit-aware admission control. If every eligible provider fails, queue/pause or fail transparently rather than automatically calling a paid model.
- Shared model resources made available to Genesis, IDE and every authorised Aetherius app with independent identities/policies.
- Local/offline support and portable deployment modes: Aetherius-hosted, hybrid, bring-your-own-provider (BYOAI), and fully local/self-hosted.

### 2B. Genesis complete solo capability

- Persistent Genesis identity separate from process ID, model weights and cloud provider.
- Shared full skills/tool library including research, coding, software builds, browser automation, test execution, document and media tasks, design/engineering/science tools and future capabilities; tool invocation is governed by permission and feasibility.
- Agent capabilities are **not locked to worker roles**. Genesis can execute the underlying task directly using shared skills without spawning that role, subject to model/hardware limitations.
- Durable goal selection for user-authorised initiative; research/experiments in sandboxes; memory of evidence, hypotheses, outcomes and past failures. Self-improvement recommendations must be measured, versioned, reversible and approved where they modify consequential components.
- Multiple ongoing strands of supervised AND personally executed work where permitted.

### 2C. Hierarchical hive, collaboration and supervision

- Genesis → dynamic team leads → specialised workers → optionally nested subagents, alongside Genesis' own active tasks; the hierarchy is flexible rather than permanently fixed.
- Every agent has unique identity, parent/lineage, mission, allowed capabilities, policy scope, execution target, model/provider, worktree, active state, communication endpoints and lifecycle events.
- Delegated scope can **only narrow**, never broaden parent permissions, access, spending authority or approved objectives.
- Worker leases, lifecycle/heartbeat validation, cancellation propagation, recursion-depth and global concurrency bounds, quota budgets, safe retry, task dependencies, event logs and clear handoff protocol.
- Agents can send DMs, hold group meetings, coordinate peer-to-peer and communicate with user independently. Shared knowledge should be published as evidence-backed artifacts/references, not blindly copied into every context.
- Independent checks and controlled integration for code/work products; file write-set conflict management and separate Git worktrees.
- Solo-vs-hive benchmarking for elapsed time, reliability, quality, total token/compute usage, communication overhead, autonomy and conflict rates. More agents is not inherently better.

### 2D. Persistent remote execution

- Real remote execution for coding/research/browser/terminal tasks, not just calls to hosted AI inference.
- Durable task registry, state machine, checkpoints, artefacts, idempotency keys, leases/heartbeats, dispatcher, worker recovery, bounded retries and backup/restore.
- Control plane (goals/policies/queues/state) independent from execution plane (model calls/agents/containers/VMs), and data plane (artifacts/logs/memory).
- Resume jobs after user/browser disconnection, local power off and recoverable remote worker failure, subject to cloud quota availability. Treat active progress versus safely paused tasks as distinct statuses.
- Remote workers through free eligible VM/container/job services, external cloud coding agents or portable self-hosted servers; run CPU-light models remotely only where hardware allows, using hosted inference for heavy models.
- Human handoff for account verification or consequential approvals; other independent branches continue where possible.

### 2E. AI-native language / agent communication

Create a first-party, **versioned and inspectable semantic message contract** expressing:

- Sender/receiver/team, task and parent IDs; intent; objective; hypotheses; evidence references; assertions with confidence; dependencies; permissions; status; requested actions; timestamps; causal trace; schema version.
- Strong JSON-schema/Protobuf/CBOR or analogous typed representation for low-overhead processing. Different encodings can be negotiated, but meaning/schema should remain stable and auditable.
- A2A or another compatible protocol for external agent/task interoperability, MCP for tools/resources, HTTP/WebSocket/gRPC as network transports where appropriate; Agent Bridge enforces identity and authorization.
- Experiment candidates: GibberLink built on GGWave (acoustic byte transport, not an LLM language), Google's interlingua research (latent representations, not a released universal wire protocol), Ainglish (human-legible ambiguity-reduction dialect), and learned/emergent agent dialects (research track, not default production communication).
- GGWave optional for nearby physical devices, robotics and constrained communications, not cloud-to-cloud default.
- Translation to human-readable records, schema validation, backward-compatible versioning, benchmarked semantic accuracy, conflict resolution and no opaque unreviewable privilege channels.
- No assumption that different models' internal embeddings/latent vectors are directly interoperable.

### 2F. Secure automated provisioning and private credentials

- Hermes/OpenCode may audit, research, navigate websites, paginate, use official APIs/CLIs, control a Windows browser/desktop when explicitly authorised, create code/configuration and use remote consoles as temporary setup operators.
- Prefer APIs and CLIs, then Playwright/CDP/browser tools, then desktop computer-use for unsupported GUI workflows.
- When a provider needs personal details, password, passkey, CAPTCHA, SMS/2FA, recovery code, accepting terms or confirmation, stop that portion, display the genuine official page, and let the user directly operate a protected form/session. Never attempt to bypass verification.
- Language model must not see plaintext secrets through prompts, terminal tool outputs, logs, screenshots, recordings or copied clipboard history. Use trusted local password managers, secret stores, credential helpers and secure CLI prompts / provider secrets. If the tool chain cannot guarantee this, disclose the limitation and use user-driven transfer instead.
- Separate website login passwords, API keys, local development tokens, encrypted cloud secrets, public provider config, recovery codes and per-worker scoped credentials. Long-lived runtime secrets must be retained securely by a trusted component; **do not promise zero retention by the entire infrastructure**.
- Use isolated browser profiles for setup, disable unneeded recording, do not read personal browsing data, rotate or revoke temporary credentials, check output for leaked keys, and store only essential audited secret references.
- Approval checkpoints for account creation, resource deployment, externally visible endpoints, permission changes, destructive actions, billing/credit-card setup and importing confidential data.

---

## 3. PROVISIONAL PROVIDER/MODEL RESEARCH CATALOGUE (REVERIFY LIVE)

**Critical caution:** The following names, promotional offers, limits and access methods came up in the 14 October 2026 conversation. None guarantees ongoing zero-cost entitlement. Check current official documentation, exact IDs, account eligibility, model APIs, privacy, licensing and terms before use. Do not embed stale claims as truth.

### Hosted model discovery priorities

- **OpenCode Zen:** zero-price/promotional catalog entries reported for Nemotron 3 Ultra, Nemotron 3.5 Lightning, Space Bunny, Muse Spark 1.3 Contributor, Xiaomi MiMo V2.6 Flash / V2.5, Big Pickle, LongCat, Ling, Exo, Fledge and Jev; free availability and exact `...-free` IDs must be verified. Inspect account/credit-auto-reload options and API eligibility. Official entry: https://opencode.ai/ and https://docs.opencode.ai/docs/zen/
- **OpenRouter:** free collection of Nemotron, Poolside Laguna, various open models etc; limited shared free request quota, model-specific privacy/training terms and short-term changes. https://openrouter.ai/collections/free-models
- **GroqCloud:** free-tier inference for eligible GPT-OSS 20B/120B and other models, with request and token budgets. https://console.groq.com/docs/rate-limits
- **Cloudflare Workers AI:** subset of models eligible for Workers Free, subject to daily neurons. Paid-only access for some previously free models illustrates entitlement churn. https://developers.cloudflare.com/workers-ai/
- **NVIDIA Build / NIM:** trial/developer-hosted inference for Nemotron and others, possibly capped; verify API entitlement. https://build.nvidia.com/models
- **Cerebras Cloud:** potential free inference, throughput and limit comparison. https://cloud.cerebras.ai/
- **Nous Portal:** potential free model access for Hermes, but **Nous-hosted Hermes Cloud computing is distinct and may not be free**. Verify terms. https://portal.nousresearch.com/
- **Kilo Code:** Auto Free and promoted models for eligible integrations; check if free access is API-accessible in a way permissible to Aetherius. https://kilo.ai/
- **Vercel AI Gateway:** reported periodic credit allowance and free-model offerings; Hobby has important non-commercial restriction; review overage/billing exposure. https://vercel.com/docs/ai-gateway/pricing
- **Google Gemini API:** eligible free-tier models, region-specific terms, privacy and billing-account implications. https://ai.google.dev/gemini-api/docs/pricing
- **Ollama Cloud, Hugging Face Inference Providers, Mistral, Cohere, Qwen, MiniMax, Kimi/Moonshot, DeepSeek:** investigate free/trial API entitlement, distinction between temporary credits and recurring free quotas, model lists and regional permissions.
- **ChatGPT/OpenAI, Claude, GitHub Copilot, Manus:** free consumer apps or subscription-entitled agent access are **not automatically permitted reusable model-server APIs**. Use documented authorised agent integrations where available, and never reverse-proxy a consumer session contrary to terms. Distinguish Claude Code cloud sessions, ChatGPT/Codex cloud work, Manus cloud computer and Copilot coding agent from general-purpose model endpoints.

### Downloadable open-weight model families to evaluate (where licence permits)

Qwen 3.x/Qwen Coder; DeepSeek / distilled variants; NVIDIA Nemotron open releases; Gemma; IBM Granite; Microsoft Phi; GPT-OSS; Devstral; Ministral; embedding models (Qwen3 Embedding, BGE, Nomic); audio models (Whisper, Piper/Kokoro); vision (Moondream, multimodal Qwen/Gemma); creative image/video (FLUX.1 Schnell, Wan). Verify release date, licence, exact weights, quantization, checksums, support for tool calls, model size and hardware constraints. Downloadability alone does not mean all uses are unrestricted or that inference is free of electricity/hardware costs.

### Candidate app/agent ecosystem (do not install everything)

Hermes, OpenCode, AionUi, Eigent, Goose, Agent Zero, UI-TARS Desktop, OpenClaw, OpenHands, Cline, Browser Use Desktop, AnythingLLM, Cherry Studio, OpenWork, Kilo Code, Antigravity, Kiro, Cursor, Copilot, Aider, Pi, Crush, Open Interpreter, Qwen Code, Gemini CLI, Langflow, Flowise, Dify, n8n, Agent-S. Determine which are free/open source/freemium, Windows-supported, tool-compatible and truly offer *new* capabilities. These applications are reference implementations and possible temporary workers/clients, not mandatory dependencies in Aetherius.

### Infrastructure candidate pool (avoid unnecessary multiplicity)

- **Cloudflare Workers**: API gateway/auth/policy checks and lightweight control functions; free-tier CPU/request limits.
- **Cloudflare Workflows/Queues**: waiting/retry and dispatch, not heavy terminal/GUI compute; quotas, retention and state lifetime must be reviewed.
- **Supabase Free / PostgreSQL**: canonical job state, task events, model registry, some auth/storage; free-project pause and storage limits; external backups.
- **Firebase Spark**: optional frontend/Auth/Firestore, but no Cloud Functions on Spark; avoid duplicating Supabase needlessly.
- **Oracle Always Free ARM VM**: candidate true persistent remote Linux agent worker, no free dedicated GPU; account/card eligibility, availability and idle reclamation restrictions.
- **Google Jules**: real asynchronous remote coding agent with an API and finite free task allowance; useful specialized external worker.
- **GitHub Actions**: bounded hosted build/test/development jobs with time/monthly limits; not an unlimited 24/7 remote desktop.
- **Cloudflare Browser Rendering**: bounded remote browser work, not unlimited desktop computing.
- **Vercel Hobby/AI Gateway**: optional free frontend/inference credit use with non-commercial restrictions and spend risk; keep replaceable.
- **Hugging Face Spaces/ZeroGPU, Kaggle, Colab**: demos and experiments; never assume free notebook sessions can be used as permanent unattended remote workers. Follow service restrictions (Colab specifically restricts some proxy/unattended usage).
- **Google Cloud Run Jobs**: possible bounded execution but may require billing and overage exposure; not strict £0 without controls and approval.
- **OpenTofu, Podman/Docker, GitHub Actions, OpenTelemetry, Prometheus/Grafana, OSV-Scanner, Syft, pg_dump**: open-source/reusable provisioning, operations and security components.

**Prefer the minimum viable set of providers:** existing Aetherius systems + one private API gateway + one durable database/state store + one genuine independent remote worker + at least two eligible free model providers. Expand only when justified by tests.

---

## 4. PRIOR IMPLEMENTATION EVIDENCE TO RECONCILE, NOT ASSUME

Earlier conversation references to historical project work included:

- Aetherius components identified as P17 state, P18 model/provider fabric, P19 workflows and skills, P20 worker fabric, P21 Agent Bridge, P22 Genesis, P23 IDE, P25 authority, P26 knowledge/memory, P27 transport, P30 resource placement, P31 provenance/evaluation/observability, plus other P16–P31 modules.
- Reported P20 worker work around commit `2921c6f`, write-set safeguards around `7a06676`, and Genesis Reflex around `dc48a76`.
- Reports of nine actual worker lifecycle/recovery tests and 1,407 Agent Bridge tests; earlier reports of specialist roles (nine), logical members (twelve), and a configured concurrency of three.
- An existing Ollama installation, model list, worker systems, model gateway and registries were referred to. One earlier response assumed a Windows PC with 16 GB RAM and GTX 1050 Ti 4 GB; **verify hardware rather than treating it as current fact**.
- A GitHub repository listing through the available connector produced no accessible repositories in an earlier assessment; **absence of visible repositories is not proof they do not exist**. Request scoped access or find the actual local source roots if needed.

Treat all of these as **leads to inspect**, not currently validated implementations. Preserve original commits, IDs, history and decisions in an evidence register. If not found, classify `NOT_LOCATED` rather than `NOT_IMPLEMENTED`.

---

## 5. CANONICAL GAP REGISTER — 42 CATEGORIES

This is the deduplicated register compiled in the chat from earlier G01–G28 and Genesis GT-01–GT-20 analyses. Do not create 42 new services. Preserve mappings from old identifiers and add exact evidence, status, severity, owner, workaround, dependencies and test IDs.

### A. Architecture, ownership and continuity — 5
- **A01 [P0]** Current implementations/deployments not independently inventoried or verified → audit code, tests, services, credentials/endpoint metadata, registry and live topology.
- **A02 [P0]** Risk of rebuilding shared mechanisms → reconcile P16–P31 ownership before new code.
- **A03 [P0]** OS/IDE/Genesis/Agent Bridge/model runtime boundaries and APIs insufficiently verified → versioned contracts and integration tests.
- **A04 [P1]** Provenance and previous experiments/decisions risk loss → permanent registry with superseded/history links.
- **A05 [P1]** Third-party lock-in risk → independent first-party interfaces and adapters.

### B. Free AI models/providers and resources — 7
- **B01 [P0]** Incomplete, changing hosted model catalogue → official live discovery and provenance.
- **B02 [P0]** Free app usage mistaken for free API entitlement → classify app, API, local weights, hosted agent, trial separately.
- **B03 [P0]** Promotional withdrawals/rate-limit changes → eligibility validity, freshness and expiry checks.
- **B04 [P0]** Risk of hidden charges/paid failover → deny-by-default zero-spend admission policy.
- **B05 [P1]** API protocol and multimodal/tool mismatch → per-provider adapters/capability negotiation.
- **B06 [P1]** No verified quality-based model selection → real task benchmarks and scored routing.
- **B07 [P1]** Token/context waste → retrieval, cache, batching, deduplication, quota-aware task scheduling.

### C. Cloud continuity and execution — 7
- **C01 [P0]** Real remote agent execution with PC off not demonstrated → deploy eligible worker or remote agent and test.
- **C02 [P0]** Jobs disappear on restart → persistent jobs, checkpoints and durable state.
- **C03 [P0]** Worker/network failure recovery incomplete/unverified → leases, bounded retries and idempotency.
- **C04 [P0]** Free-cloud limited availability → portability, pause/resume, eligible fallback and offline queueing.
- **C05 [P1]** Cloud GUI/browser tools unavailable/incomplete → remote Playwright/CDP and authorised desktop targets.
- **C06 [P1]** Cloud state loss/corruption risk → encrypted backups and restoration tests.
- **C07 [P1]** Different devices out of sync → events, reconnect, replay, authoritative state.

### D. Genesis, teams and active hive — 8
- **D01 [P0]** Solo Genesis skill parity not verified → direct shared skills/capability registry; solo execution tests.
- **D02 [P0]** Genesis identity/memory/goal continuity unverified → state outside model/worker processes.
- **D03 [P0]** Active Genesis contributions WHILE supervising not demonstrated → separate working and supervisory task loops.
- **D04 [P0]** Dynamic nested delegation safety unverified → parent lineage, scoped capability tokens, depth/budget limits and cancellation.
- **D05 [P1]** Team identities/roles inconsistent → canonical roster and direct addressing.
- **D06 [P1]** Shared knowledge fragmented → scoped provenance-backed semantic evidence fabric.
- **D07 [P1]** Unattended initiative and reversible improvement unproven → bounded goals/experiment queues with evaluation.
- **D08 [P1]** Benefit of hive vs Genesis alone unknown → controlled solo/hive benchmarking.

### E. Language, semantics and interoperability — 5
- **E01 [P0]** No verified canonical typed semantic contract → schema with tasks/evidence/intent/permissions/provenance.
- **E02 [P1]** Cross-model semantic drift → validation, translation and roundtrip tests.
- **E03 [P1]** External agent protocol mismatch → A2A/MCP adapters, preserving distinct roles.
- **E04 [P2]** Emergent/Ainglish advantage unverified → sandbox benchmarks and revertible conventions.
- **E05 [P0]** Insufficient human auditability → replayable, readable and linked communication logs.

### F. Automated setup, data protection, security — 6
- **F01 [P0]** End-to-end agent provisioning not demonstrated → Hermes/OpenCode trusted tools, CLI/browser/desktop process.
- **F02 [P0]** Sensitive onboarding/2FA handoff needed → direct user interaction in protected environment.
- **F03 [P0]** Secret exposure risk → vault/helper, no model plaintext and audited injection.
- **F04 [P0]** Nested worker permission escalation risk → P25 authorisation at every transition/tool call.
- **F05 [P0]** Prompt injection and malicious external-page risk → origin checks, allowlists, sandbox and approved actions.
- **F06 [P1]** Licence/region/privacy/free-tier mismatch → policy and eligibility register.

### G. Proof, operations and continuous quality — 4
- **G01 [P1]** UI may claim activity without live evidence → heartbeats, process IDs, timestamps, provider job IDs, real traces.
- **G02 [P0]** Plausible agent reports mistaken for results → independent artifacts/tests/review.
- **G03 [P1]** Regression and supply-chain failures → signed/reproducible builds, scanning, CI/CD and rollback.
- **G04 [P1]** Discovery monitoring not tied to runtime routing → keep external discovery separate, integrate validated change events.

**Earlier gap labels G26 and G27:** G26 was persistent independent cloud execution; G27 was Genesis persistent cloud existence/hierarchical supervision. **G28:** AI-native/semantic communication. These are captured across C/D/E. Preserve the old-to-new mapping; do not lose them.

---

## 6. PRACTICAL WORKAROUND POLICY — AVOID OVERENGINEERING

Prefer the **smallest independently testable mechanism** that closes the gap:

| Hard enterprise concern | First practical solution | Escalate only when needed |
|---|---|---|
| Distributed workflows | Existing P19/P20 with PostgreSQL durable state; evaluate DBOS | Temporal if operationally justified |
| Agent team framework | Existing Genesis/P20 worker mechanisms; borrow patterns from Microsoft Agent Framework/LangGraph | New orchestration framework only if gaps proven |
| Cloud persistence | Eligible remote VM + durable queue + resumable jobs; Jules for coding | Paid GPUs/enterprise hosting only after explicit future decision |
| Scale | Queue/admission control and quotas | Kubernetes/Kafka/multiregion only if demonstrated need |
| Identity | Existing P25 plus scoped tokens and hosted Auth/vault | Full identity federation as necessary |
| Inference gateway | Existing P18 + lightweight provider adapters | LiteLLM or larger router if proven safer/better; verify supply-chain advisories |
| Monitoring | Structured events/OpenTelemetry and small dashboard | Full distributed observability stack later |
| Browser provisioning | Official APIs/CLIs, Playwright/CDP, then desktop control | Human handoff when required |
| AI language | Typed semantic schema and refs | Ainglish/emergent dialects after evidence of benefit |
| Cross-device connectivity | SSH / WireGuard / Tailscale / secure authenticated API | Complex distributed mesh only if required |
| Backups | PostgreSQL dump + encrypted off-provider backup + restore test | Advanced replication when needed |

Do not build an agent skill in Hermes and separately reimplement it for OpenCode if one reusable Aetherius-native skill/tool adapter can serve both. Avoid installing all candidate tools merely to increase tool count.

---

## 7. SECURE AGENT-OPERATED INSTALLATION / ACCOUNT ONBOARDING PLAN

### Operator split
- **Hermes:** Preferred temporary primary GUI/browser/computer-use operator if its actual installed version exposes supported Windows automation; also terminal and subagent orchestration.
- **OpenCode:** Parallel code/audit/test worker, optionally browser/computer-use through authorised plugins/MCP/tools.
- **Genesis (when implemented/verified):** Long-term first-party orchestrating intelligence; Hermes/OpenCode eventually removed as required dependencies.

### Automation sequence
1. Audit local programs, files, existing models and cloud resources **without altering state**.
2. Research official provider endpoints, free-tier restrictions, account signup requirements and terms; use APIs/pagination/structured data over screenshots where possible.
3. Build all non-secret provisioning code, config templates, policy, tests and rollback plans locally.
4. Produce a **short approval checkpoint** before each consequential account registration, billing change, remote resource deployment, public exposure or permission grant. List provider, intended resources, free eligibility, data transmitted and rollback.
5. Open official site or CLI; user enters personal details, passwords, 2FA and consent DIRECTLY, with screen/capture masking and isolated profile. The agent may resume once the trusted helper returns success.
6. Install API keys through an encrypted vault, OS credential manager or a provider-native secret setting CLI. Do not place secret contents in prompts, stdout, shell history, plaintext config or ordinary clipboard when alternatives exist.
7. Deploy only approved £0-eligible resources, keeping APIs private or authenticated; block accidental open public proxies and paid usage.
8. Run real smoke/functional/security tests, collect redacted logs, remove temporary sessions, and write a current configuration/secret-reference register.

**Nuance:** Some apps/GUI drivers may capture screenshots containing credentials. Verify what each tool records and where it sends data. Do not promise secrets are excluded if that cannot be demonstrated. If exposed, stop, notify the user and guide rotation.

---

## 8. END-TO-END FUNCTIONAL ACCEPTANCE TESTS

Implement repeatable, evidence-producing tests. At minimum:

- **AT-01 Genesis Solo:** Complete a representative research+coding+tool-use task without subagents, with tests/evidence.
- **AT-02 Genesis Works + Supervises:** Genesis performs active work while monitoring multiple workers.
- **AT-03 Nested Team:** Lead deploys at least one authorised subagent; lineage, bounded scopes, budget and cancellation verified.
- **AT-04 Hive Communication:** Facts, hypotheses and task events shared with provenance and correct recipients, readable audit history.
- **AT-05 PC-Off Cloud:** A real remote job progresses while Windows PC is shut down; evidence from remote provider logs/events, not self-report.
- **AT-06 Crash Recovery:** Kill/restart remote worker; checkpoint restores work without duplicated external side effects.
- **AT-07 £0 Guard:** API rejects paid endpoint, unknown billing status, exhausted quota and any unauthorised paid fallback.
- **AT-08 Onboarding:** At least one provider provisioned through private human handoff, non-secret config generated automatically.
- **AT-09 Secret Isolation:** Model and logs do not receive plaintext keys; scope and rotation tested.
- **AT-10 Browser:** Authorised browse/pagination/extraction/form automation performed with testable provenance.
- **AT-11 Direct Agent Chat:** User addresses an individual live team member; Genesis still supervises; conversation persists.
- **AT-12 Cross-Project:** Genesis, IDE and a separate Aetherius client use one provider gateway with separate privileges.
- **AT-13 Provider Replacement:** Swap model/provider without losing agent/task identities or memory.
- **AT-14 Language Benchmarks:** Compare plain English, structured schema, Ainglish, semantic references and experimental dialects on semantic accuracy, latency, total tokens, reliability and interpretability.
- **AT-15 Solo vs Hive:** Controlled end-to-end comparison measuring wall time, cost/compute, quality and communication overhead; hive proves useful rather than simply producing more tokens.
- **AT-16 Disaster Restore:** Restore backup in clean environment and check identities, tasks, models, roles, permissions, logs and data integrity.
- **AT-17 Security:** Prompt injection cannot override P25 access rights; nested agents cannot escalate; private data routing blocked.
- **AT-18 Provider Withdrawal:** Simulate a free model moved behind a paywall; route is disabled, tasks deferred or eligible alternate chosen with no paid usage.
- **AT-19 Replay and Observability:** Every actual tool call ties to agent ID, task ID, model ID, outcome, trace and artifacts.
- **AT-20 No-Aetherius-Dependency-on-Hermes:** Prove representative Genesis/IDE model/tool tasks work when Hermes and OpenCode are not running.

For each test, record: test name, repository commit/version, exact environment, model/provider, timestamp, input (redacted where necessary), expected, actual, artifact links, run ID, pass/fail, cause and fix.

---

## 9. DELIVERY PHASES — CONTINUE AUTONOMOUSLY WITHIN AUTHORITY

**Phase 0 — Evidence inventory (start here):** Locate local repositories/connected project files, prior specs, skill registry and architecture documentation. Inspect P16–P31 and related implementations. Run read-only tool discovery and safe available tests. Build an evidence-based `EXISTS / IMPLEMENTED / TESTED / INTEGRATED / DEPLOYED / VERIFIED / NOT_LOCATED / BLOCKED` register and old-to-new gap mapping.

**Phase 1 — Reconcile boundaries:** Confirm shared service ownership, avoid duplicate worker/memory/model/security registries, and define versioned API contracts only where missing. Capture compatibility/rollback plan.

**Phase 2 — Free-provider catalogue and £0 policy:** Inventory and actually test at least two eligible hosted model providers plus local inference if available. Verify exact model IDs, per-account entitlements, data policy and tool-calling support. Put zero-paid-fallback and privacy checks in the router.

**Phase 3 — Persistent control/state:** Connect the existing task layer to a durable store/queue, checkpoints, worker leases, traces and backup/restore. Choose the simplest tested existing library; no new general-purpose orchestration product by default.

**Phase 4 — Real remote worker:** With explicit approval/account access, deploy one true independent cloud worker or external cloud coding agent; verify PC-off operation, remote artifacts, user reconnection and crash recovery.

**Phase 5 — Genesis solo + active hive:** Prove solo tool access, then Genesis active work + team supervision, nested delegation, independent agent chats and no privilege escalation.

**Phase 6 — Secure setup skills:** Turn audited cloud onboarding and credential handoff into a reusable Aetherius-owned provisioning skill/workflow compatible with current Hermes/OpenCode operator and future native IDE.

**Phase 7 — Communication research:** Integrate canonical typed message protocol and human-readable log; benchmark optional Ainglish, binary representations, semantic refs and emergent dialects. GGWave only where acoustic links are useful.

**Phase 8 — Industrial-style hardening:** CI/CD, sandbox and supply-chain verification, observability, backup restores, quotas/rate-limit fault injection, disaster recovery, device-aware interfaces, rollbacks and acceptance-test evidence.

Keep each phase small and working. A blocked account creation should not stop independent authorised coding, research and testing.

---

## 10. OUTPUT CONTRACT: WHAT TO GIVE THE USER

At each material milestone provide:

1. **What was discovered** (actual repositories, current software versions, prior decisions, discovered endpoints and free-tier eligibility).
2. **What already works** (with directly reproducible evidence, not verbal claims).
3. **What was implemented or changed** (files, commits, migrations, commands, configuration, deployment IDs, rollback paths).
4. **What was tested and what failed** (real logs and artifacts; redact secrets).
5. **Open canonical gaps** (A01–G04, plus old G/GT mappings), owner/dependencies, workaround, priority and next proof required.
6. **Precise user action required** (only where necessary, e.g. which official page to approve, where to enter private data, and no secret pasted back into chat).
7. **Resources/costs** (accounts used, verified monthly/daily quotas, estimated consumption, remaining free resources, charge-risk controls).
8. **Integrity of Genesis** (identity continuity, ongoing tasks, worker parentage, delegation permissions, agent availability, solo/hive comparison).
9. **Portability** (how to replace a provider/worker/store without redesigning Aetherius and how to remove Hermes/OpenCode as dependencies).
10. **Recommended next executable step**, and continue implementing authorised tasks rather than repeatedly waiting for instructions.

Use an exact evidence vocabulary:
- `PROPOSED` — described only.
- `FOUND` — referenced in the current code or documentation.
- `IMPLEMENTED` — concrete code exists.
- `TESTED` — repeatable tests were run, with run evidence.
- `INTEGRATED` — connected to real dependent systems.
- `DEPLOYED` — reachable/running in the claimed target environment.
- `INDEPENDENTLY_VERIFIED` — evidence from a second check/method supports results.
- `NOT_LOCATED` — source/runtime not accessible or not found; do not equate with nonexistent.
- `BLOCKED` — named dependency/approval missing.

**First response expected from executing operator:** Identify the actual current Aetherius root directories/repositories and installed tools; present the smallest safe immediate execution plan; start the evidence inventory and non-sensitive tests; report only specific access/approval blockers. Do not claim cloud services or the full hive have already been deployed.

---

## 11. ESSENTIAL RESEARCH LINKS (REFERENCE, NOT PROOF OF CURRENT ENTITLEMENT)

**Agents and tools:**
- Hermes Agent: https://github.com/NousResearch/hermes-agent
- OpenCode: https://github.com/anomalyco/opencode
- AionUi: https://github.com/iOfficeAI/AionUi
- Eigent: https://github.com/eigent-ai/eigent
- Goose: https://github.com/aaif-goose/goose
- Agent Zero: https://github.com/agent0ai/agent-zero
- UI-TARS Desktop: https://github.com/bytedance/UI-TARS-desktop
- OpenHands: https://github.com/OpenHands/OpenHands
- Cline: https://github.com/cline/cline
- Browser Use Desktop: https://github.com/browser-use/desktop
- Microsoft Agent Framework: https://github.com/microsoft/agent-framework
- LangGraph: https://github.com/langchain-ai/langgraph
- DBOS: https://github.com/dbos-inc/dbos-transact-py
- Temporal: https://github.com/temporalio/temporal

**Inference and interoperability:**
- Ollama: https://github.com/ollama/ollama
- llama.cpp: https://github.com/ggml-org/llama.cpp
- vLLM: https://github.com/vllm-project/vllm
- SGLang: https://github.com/sgl-project/sglang
- LiteLLM: https://github.com/BerriAI/litellm (verify release security)
- A2A protocol: https://a2a-protocol.org/
- MCP: https://modelcontextprotocol.io/
- GGWave: https://github.com/ggerganov/ggwave
- GibberLink: https://github.com/PennyroyalTea/gibberlink
- Ainglish: https://www.ainglish.org/

**Cloud and model providers:**
- Cloudflare Workers: https://developers.cloudflare.com/workers/
- Cloudflare Workflows: https://developers.cloudflare.com/workflows/
- Cloudflare Workers AI: https://developers.cloudflare.com/workers-ai/
- Supabase: https://supabase.com/pricing
- Firebase: https://firebase.google.com/pricing
- Vercel AI Gateway: https://vercel.com/docs/ai-gateway/pricing
- Oracle Cloud Free: https://www.oracle.com/cloud/free/
- Google Jules API: https://jules.google/docs/api/reference/
- GitHub Actions: https://docs.github.com/actions
- OpenRouter Free: https://openrouter.ai/collections/free-models
- Groq: https://console.groq.com/docs/rate-limits
- Gemini API: https://ai.google.dev/gemini-api/docs/pricing
- NVIDIA Build: https://build.nvidia.com/models
- Ollama library: https://ollama.com/library

**Free resource discovery:**
- https://github.com/surendranb/free-inference
- https://github.com/build996/free-ai-api-benchmark
- https://github.com/Reveritus/Free-LLM-API-resources

## 12. CURRENT STATUS AND MONITORING NOTE

An **Aetherius Free AI Watch** daily conditional monitoring task was created in ChatGPT during this conversation to track meaningful changes in free models, provider limits, security/privacy/licensing, cloud services and viable infrastructure alternatives. **This monitoring is external to Aetherius and is NOT an implemented Aetherius provider-discovery microservice.** Do not assume Hermes/OpenCode or deployed Aetherius can access its internal state automatically; provide a native discovery/monitoring adapter if needed.

At the time of this handoff, the shared Aetherius cloud, Genesis persistent cloud worker, independent live hive integration, adaptive AI-language benchmark, multi-provider gateway and full end-to-end tests **were discussed but not verified as deployed in the current environment**. Historical implementation claims require inspection. No cloud credentials, passwords or API keys are included.

## 13. STOP CONDITIONS / APPROVAL GATES

Proceed with authorised, reversible, non-sensitive work. Pause and request explicit permission only for:
- Creating or substantially modifying external accounts and terms commitments.
- Entering personal information, passwords, 2FA, identity verification and payment details.
- Activating billing or accepting any potential charge, even if a free quota is offered.
- Provisioning/deleting externally hosted infrastructure; modifying existing live endpoints or secrets.
- Publishing proprietary project data, code or identifiable information to external model services where routing is not already approved.
- Destructive filesystem/repository changes, privilege escalation, unbounded autonomous execution, unattended real-world hardware controls, or other consequential external actions.

**FINISHING PRINCIPLE:** Deliver actual tested useful work and an evidence-backed handover. Where free services cannot meet a requirement, provide a compliant workaround (deferred execution, self-hosting, alternative free provider, modified scope) and say exactly what remains unachievable under strict zero spend.


---

## 14. POST-HANDOFF COMPLETENESS REVIEW — OPERATIONAL CLARIFICATIONS (15 OCTOBER 2026)

These clarifications are **not evidence of defects** or proof that code is absent. Most refine existing A/B/C/D/E/F/G requirements that were specified but not operationally detailed. Preserve all 42 original canonical IDs; record the clarifications below as mapped child requirements rather than creating duplicate services or renumbering history. New acceptance scenarios AT-21–AT-32 supplement AT-01–AT-20.

### H01. Individual owner now; future multi-user and organisational isolation (maps A03, F04, F06, B04)

- Begin with a single-owner, private deployment, but define tenancy/workspace/organisation boundaries that can later support multiple Aetherius users and organisations without a data-model rewrite.
- Separate the Aetherius platform administrator, human user, Genesis identity, team leader, subagent, service account, and provider credential. Tokens, model quotas, knowledge and audit access belong to specific authorised scopes.
- Enforce cross-tenant isolation at **API, database, vector search, cache, model-gateway, object storage, messaging and backup/export** boundaries; never rely only on frontend permissions.
- Apply per-user and per-workspace quota/budget reservations and abuse limits if the system later becomes publicly accessible; prohibit sharing user provider keys outside their authorised scope.
- Future commercial deployment is a separate entitlement/licensing and data-protection decision. Personal, non-commercial hobby/free tiers must not be quietly used for commercial Aetherius services.

### H02. Global kill switch, pause, recall and emergency credential revocation (maps D04, F04, C03, C07)

- Provide owner-controlled emergency stop for Genesis, a team, an individual worker, a single tool, a provider account, or all external actions. Explicitly distinguish **pause for resumption**, **cancel task**, **revoke authority**, and **emergency halt**.
- Fan out revocation to nested workers and remote systems via short-lived leases/tokens; a disconnected worker must fail closed when its lease expires.
- Record revoked capabilities and block further side effects *even if an old model response arrives later*. Reconcile in-flight operations, rollback reversible changes, and explicitly report non-reversible actions that already completed.
- The safety/authority layer owns emergency action enforcement. Genesis cannot overrule it or assign itself new permissions.

### H03. Versioned skill acquisition and Genesis solo capability parity (maps D01, D07, A04, G02)

- All genuinely reusable worker skills, tool manifests and workflows must be discoverable through the shared Aetherius skills registry so Genesis can invoke the *same underlying capability* directly where authorised.
- A useful skill discovered by any subagent enters a **candidate → provenance/licence review → sandbox tests → security review → benchmark → approved release → registry publication** pipeline.
- Version, sign or hash skill packages, declare required tools/model capabilities/OS/dependencies/permissions, and maintain a tested rollback path. Untrusted worker output must not self-install as a privileged production skill.
- Genesis must be able to complete the core skill's benchmark task alone without artificially requiring a worker role. Specialist workers can still outperform it by model capability or dedicated tooling; measure this distinction.
- Preserve unsuccessful experiments and superseded versions rather than erasing results. First-party portable skill definitions should be reusable by Hermes/OpenCode during bootstrapping but remain owned by Aetherius.

### H04. Quantitative service objectives and bounded cloud continuity (maps C01–C04, G01–G02)

- Define explicit, measured initial targets **before** promising continuous cloud execution: task checkpoint frequency, maximum tolerable state loss (RPO), recovery objective (RTO), worker heartbeat expiry, job start latency, retry budget, cloud-provider failover time, and maximum acceptable user-visible stale state.
- Set numerical targets after benchmarking available free hardware and providers; don't invent guaranteed SLAs. Record best-effort targets separately from contractual guarantees, which free plans generally do not provide.
- Define state machine transitions such as `RUNNING_REMOTE`, `WAITING_APPROVAL`, `WAITING_QUOTA`, `CHECKPOINTED`, `RECOVERING`, `FAILED`, `COMPLETED_VERIFIED` and ensure UI uses actual backend evidence.
- Test power-off and provider failure scenarios using independent remote logs, not self-reported agent messages.

### H05. Energy/resource governor and workload admission control (maps B04, B07, C04, D04, D08)

- Inventory existing P30/resource governor code and measured CPU, RAM, GPU/VRAM, swap, queue depth, disk I/O, bandwidth, energy/power where available, thermal limits, and per-provider RPM/TPM/daily entitlements. Do not create a competing resource governor.
- Admission control should reserve capacity before starting a task and throttle/pause safely under pressure, including nested subagent fan-out and retry storms.
- Optimise for wall-clock success, quality, total tokens, reliability, energy and cost **together**, not maximum agent count or peak throughput alone.
- Track quotas centrally but acknowledge provider-side counts can differ; fail closed when billing/free eligibility is uncertain. Prefer accounts without payment methods or genuine hard upstream spending limits when strict zero-new-spend is required.

### H06. Semantic conflict handling and collective evidence quality (maps D06, E01–E02, E05, G02)

- Worker messages must distinguish observation, quoted source, claim, inference, hypothesis, unresolved contradiction, and independently verified conclusion; carry provenance and timestamps.
- When agents disagree, preserve the competing views and evidence. Assign follow-up experiments or independent reviewers; do not treat a majority vote, shortest message or most confident wording as proof.
- A shared hive blackboard should publish only typed claims/references under permission scopes; memory updates require versioning and conflict-resolution rules rather than unsafely overwriting earlier state.
- AI-native dialect/encoding optimisations must preserve enough causal and human-readable information for incident review, quality testing and authority enforcement.

### H07. User notifications, approvals, return-to-session experience (maps D05, C07, F02, G01)

- Define user-configurable notification priority and delivery channels for task completion, urgent faults, requests for approval, compromised credentials, exhausted free quotas, and material new research findings.
- Support **pause only the blocked branch** while unrelated authorised teams continue. Record who approved what, under which scope, with what expiry; never reinterpret silence as approval.
- On reconnect, provide a trusted delta report: actions completed, actual artefacts, failures, model/provider usage, changed files, pending approvals and upcoming work. Provide direct conversation access to individual workers and genuine meeting/event transcripts.
- Do not send private code, API secrets, personal information or confidential summaries through unapproved notification channels.

### H08. Operator handoff, ownership, export, migration and decommissioning (maps A04–A05, C06–C07, F03, G03)

- Document an Aetherius-owned operator runbook: how to provision from a clean machine, inspect the running system, rotate credentials, migrate providers, restore Genesis state, safely update/deploy components and entirely remove the temporary Hermes/OpenCode dependency.
- Test exports/imports of canonical tasks, agent IDs, knowledge/provenance, artefacts, provider metadata, policies and audit records. Avoid hidden managed-provider-specific IDs becoming permanent project identities.
- Define a reversible cloud **offboarding** path: revoke keys/tokens, disable remote workers, remove resources/permissions and confirm user-requested data deletion to the extent the provider supports it. Backups, retention and required audit records have separate policies.
- Define account-recovery and disaster-recovery custody outside a single agent's memory; store recovery material only in trusted user-controlled systems.

### H09. Legal, safety and confidential-data classification (maps F04–F06, B02, B04)

- At model routing time, evaluate source-code/data sensitivity and whether free provider terms permit retention, training, commercial use, region-specific operation and onward processing. Where a route is unsuitable, choose a permitted local/provider route or safely defer the task.
- Prepare a documented privacy/retention/deletion and user-consent model before exposing Aetherius to unrelated users. UK and other jurisdictions may impose additional obligations; obtain appropriate legal review for public/commercial deployment.
- Model/provider licences differ from SDK/UI licences and from the rights to generated artefacts. Keep a separate licence ledger covering model weights, software, datasets, icons/assets and training sources where applicable.
- For robotics and connected hardware, separate simulation/testing from live actuation. Require hardware-specific interlocks, safe-state behaviour, device limits and authorisation; never allow model-text commands directly to control consequential devices.

### H10. Trust boundary and incident response across the entire hive (maps F03–F05, E05, G03)

- Treat agent messages, generated code, logs, retrieved web pages, tool outputs, repository README files, model replies and external services as **untrusted** unless verified. Sign/attest sender and capability where feasible.
- Never allow a malicious worker or prompt-injection payload to modify system instructions, grants, route private data to an unapproved provider, create paid resources or enable unsafe tools.
- Define security-incident handling: freeze affected work, revoke scopes, quarantine artefacts, inspect provenance/logs, notify the owner, rotate impacted secrets and validate recovery before resuming.
- Security telemetry should be privacy-preserving. Access to logs, traces and screen recordings is permission-controlled; avoid retaining secret-bearing screenshots.

### H11. Model asset lifecycle and first-party runtime evolution (maps A05, B01, B05–B06)

- Preserve the longer-term first-party Aetherius model runtime and model-hub direction: model discovery, lawful download/hosting, versioned weights, checksums, compatibility, quantisation, lifecycle management, inference and serving.
- Add optional tracks for fine-tuning/evaluation and derivative models *only* where compute, model licence, data consent and quality gates permit. These are not prerequisites for the first free-cloud gateway milestone.
- Treat every model and provider as a versioned asset with capability tests and upgrade/rollback records; a marketing model family name is not enough to identify the actual weights or service revision.

### H12. Realistic minimum useful deployment, commercial boundary and progress gates (maps A01, B04, C01, D01–D04, G02)

- Initial private release scope: existing Aetherius orchestration and state + one authenticated shared model gateway + two independently authorised free inference routes + one real remote execution target + Genesis solo capability + one small supervised live team.
- Keep the first deployment **single-owner/private** and minimise providers. Later multi-user/commercial packaging requires separate security, entitlement, budget and operational verification.
- Define success using completed tasks and verifiable artefacts, not numbers of signed-up providers, subagents or installed frameworks.
- Before introducing new code, inspect actual architecture roots, current registry IDs, files, APIs, tests and resource-governor behaviour, including any local daemon/worker-state/event-stream implementations. Never replace previously working infrastructure on the assumption it is absent.

### Additional acceptance scenarios (supplement AT-01–AT-20)

- **AT-21 Emergency recall:** Revoke one nested team’s tool authority remotely, confirm both active/queued child actions stop or safely expire, and verify parent tasks remain correctly scoped.
- **AT-22 Multi-tenant isolation simulation:** Two synthetic users/workspaces cannot access each other's tasks, embeddings, files, logs, credentials, free quotas or caches even with direct API calls.
- **AT-23 Skill promotion:** A worker contributes a new skill candidate; provenance/tests/security review precede release; Genesis can invoke the approved skill alone, and rollback works.
- **AT-24 Recovery objectives:** Measure RTO/RPO, checkpoint loss bounds and user-visible state freshness under worker and cloud failures; label targets as best-effort if no provider SLA exists.
- **AT-25 Resource pressure:** Simulate quota exhaustion and critical local memory/CPU pressure; prevent oversubscription and runaway nested spawning; report actual remaining resources.
- **AT-26 Evidence conflict:** Two workers deliver contradictory claims; both are retained, independently evaluated and resolved or correctly marked uncertain rather than silently merged.
- **AT-27 User approval and notification:** An approval-required branch pauses, other branches continue, notification contains no secrets, and user can resume from another device with a complete audit trail.
- **AT-28 Cloud offboarding:** Revoke a provider's credentials, disable workers and remove remote deployment while preserving an exportable Aetherius-owned state backup and testing restore elsewhere.
- **AT-29 Confidential route:** Mark a repository or dataset confidential; ensure no agent/tool/model can send it to a free hosted endpoint whose terms are unapproved.
- **AT-30 Physical-world safety:** Simulated hardware action is allowed in sandbox; unauthorised live device actuation is blocked, and safety stop prevails over agent commands.
- **AT-31 Incident response:** Inject a malicious worker/tool output; confirm containment, denial, scoped revocation, audit evidence and safe resumption.
- **AT-32 Public-product boundary:** A free personal/non-commercial third-party entitlement is refused for a simulated multi-user/commercial Aetherius workload.

### Operator interpretation

This review **does not authorise** cloud deployment, user-account registration, billing enablement, public exposure, credential transmission or physical actuation. Existing approval gates still apply. The additions define the target behaviour and tests; use the actual system audit to mark each as `IMPLEMENTED`, `TESTED`, `BLOCKED`, `NOT_LOCATED`, etc. Report genuine overlap with existing P16–P31 implementations and preserve them as authoritative where verified.
