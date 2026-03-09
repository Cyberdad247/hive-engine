# 🐝 HIVE ENGINE — Claude Code Bootstrap Prompt
# ─────────────────────────────────────────────
# Paste this entire file as your first message in a new Claude Code session,
# or save it as .claude/bootstrap.md and reference it with:
#   > Read .claude/bootstrap.md then begin
# ─────────────────────────────────────────────

---

You are operating inside the **HIVE Engine** project — a persona-driven AI engineering assistant with model-agnostic routing via LiteLLM.

---

## 1. What HIVE Is

HIVE is a **multi-agent CLI + MCP server** built around 8 specialised AI personas. Each persona is defined by three things: a system prompt, an allowed toolset, and a model tier. They are not cosmetic — Sentinel literally cannot write files. Forge cannot plan. These constraints are structural, not instructional.

```
Forge   🔧  Code generation     ← your primary workhorse
Oracle  👁️  RPI planning        ← always start complex tasks here
Sentinel🛡️  Security review     ← runs on every Forge output
Debug   🐞  Auto-healing        ← broken Python → max 3 fix attempts
Muse    📝  Prompt optimiser    ← 3 rewrites: precise / constrained / creative
Coda    ✨  Compression         ← compresses sessions to anchors, verifies assertions
Aegis   ⚔️  Red team            ← finds attack vectors, outputs SHIP/HOLD/REDESIGN
Apis    🕷️  Browser automation  ← generates Playwright tests + crawl scripts
```

**Model Tiers** (configured in `core/router.py` via `MODEL_LADDER`):

| Tier | Default Model | Used By | Rationale |
|------|--------------|---------|-----------|
| 1 (light) | `claude-haiku-4-5` | Sentinel, Coda | High-volume, low-cost review/compression |
| 2 (standard) | `claude-sonnet-4-6` | Forge, Oracle, Debug, Muse, Apis | Balanced cost/capability for core work |
| 3 (heavy) | `claude-opus-4-6` | Aegis | Maximum reasoning for adversarial analysis |

Override any tier via `HIVE_MODEL` in `.env` or per-call in `core/router.py`. LiteLLM supports Anthropic, OpenAI, Ollama, and any OpenAI-compatible local endpoint — see [LiteLLM providers](https://docs.litellm.ai/docs/providers) for configuration.

The **auto-pipeline** (`/run` or `hive_pipeline`) chains: Oracle → Forge → Sentinel + Aegis (parallel via asyncio).

---

## 2. Bootstrap Sequence (Run Once on Fresh Clone)

```bash
# Clone
git clone https://github.com/cyberdad247/hive-engine.git
cd hive-engine

# Install
pip install litellm

# Configure
cp .env.example .env
# Open .env and set: ANTHROPIC_API_KEY=your-key-here
# Optional:         HIVE_MODEL=claude-sonnet-4-6
#                   LITELLM_LOG=ERROR

# Register with Claude Code
claude mcp add hive python $(pwd)/mcp_server.py
claude mcp list   # should show hive · 15 tools

# Verify everything works
python scripts/verify.py             # all checks must pass before any work begins
python scripts/lint.py --no-info     # must show 0 errors
python scripts/task_manager.py list  # see what's in the backlog
python cli.py
```

If verify fails — stop, diagnose, fix. Do not proceed with any task until all checks are green.

First task to run once you're inside the CLI:
```
hive > /run build a hello world FastAPI endpoint with JWT auth
```
That exercises the full pipeline and proves the environment is working end-to-end.

---

## 3. Persona Routing Rules

**Always route to the right persona. Never use a generic response when a persona is more appropriate.**

| You want to... | Use | MCP tool |
|----------------|-----|----------|
| Plan a multi-file feature | Oracle | `hive_oracle` |
| Write or edit code | Forge | `hive_forge` |
| Review a diff or file for secrets/vulns | Sentinel | `hive_sentinel` |
| Fix a broken Python file automatically | Debug | `hive_heal` |
| Rewrite a weak prompt into 3 variants | Muse | `hive_muse` |
| Compress a long session or source file | Coda | `hive_coda_compress` |
| Find attack vectors before shipping | Aegis | `hive_aegis` |
| Generate a Playwright UI test | Apis | `hive_apis_test` |
| Run the full end-to-end pipeline | Pipeline | `hive_pipeline` |
| Search past memory semantically | Memory | `hive_memory_search` |

**For any task touching > 1 file: always start with `hive_oracle` to get a task DAG first.**

---

## 4. RPI Workflow (Required for Multi-File Tasks)

```
RESEARCH  →  PLAN  →  IMPLEMENT
```

1. `hive_oracle("<your task>")` — produces a structured task DAG with constraints
2. `hive_forge("<oracle brief>")` — implements each task item in the DAG
3. `hive_sentinel("<file>")` — reviews every diff before it touches disk
4. `hive_aegis("<file>")` — red teams if the feature is security-sensitive

Shortcut: `hive_pipeline("<task>")` runs all four with Sentinel + Aegis in parallel.

**Error Recovery:**
- If `hive_heal` exhausts 3 fix attempts → it stops and surfaces the error trace. Escalate manually: read the traceback, fix the root cause in Forge, then re-run heal.
- If `hive_sentinel` blocks a diff → do not bypass Iron Gate. Remove the flagged pattern, then re-submit.
- If `hive_aegis` returns `HOLD` or `REDESIGN` → address the findings before shipping. Re-run Aegis to confirm `SHIP`.

---

## 5. Swarm Topology

For complex multi-file tasks using Claude Code agent teams:

```
HIERARCHICAL (coding tasks — always use this):
  Coordinator: Oracle  →  breaks work into DAG
  Workers:     Forge × N  →  parallel implementation
  Reviewer:    Sentinel   →  reviews each diff
  Validator:   Debug      →  runs and heals failures

MESH (research only):
  All agents share context, no coordinator
  Use only for: architecture decisions, research synthesis
```

**Always use hierarchical for coding. Mesh topology on code tasks causes context bleed and conflicting writes.**

---

## 6. File Structure & Ownership

```
cli.py              → Main CLI entry. Owns command routing.
mcp_server.py       → MCP server. 15 tools. JSON-RPC over stdio.
VERSION             → Single source of truth for semver.
CHANGELOG.md        → Auto-generated at version bump. Manual edits allowed for corrections.
TASK.md             → Auto-managed by task_manager.py. Never edit manually.
VERIFICATION.md     → Auto-updated by verify.py after each run.

core/
  router.py         → LiteLLM model routing + MODEL_LADDER. Edit with care.
  memory.py         → RAM tiered memory (working → compressed → archival).
  memory_db.py      → SQLite persistence. 6 tables. Schema is fixed.
  hnsw.py           → Pure-Python HNSW vector index. Zero external deps.
  pipeline.py       → Auto-pipeline + async execution. Core orchestration.
  feedback.py       → Rating → rule extraction → system prompt injection.

personas/
  base.py           → Base Persona class. Always-on secret gate lives here.
  forge.py          → Code generation. Model tier 2.
  oracle.py         → RPI planner. Model tier 2.
  sentinel.py       → Security + Iron Gate. Model tier 1.
  debug.py          → Auto-healing loop (max 3 attempts, then escalate to user). Model tier 2.
  muse.py           → Prompt optimiser. Model tier 2.
  coda.py           → Compression + assertion verifier. Model tier 1.
  aegis.py          → Red team adversary. Model tier 3.
  apis.py           → Playwright automation. Model tier 2.

scripts/
  verify.py         → 31 checks. Run before every commit. CI gate.
  lint.py           → HIVE-specific static analysis. 15 rule codes.
  version.py        → Semver: bump / tag / rollback / changelog.
  edge_build.py     → AST minifier → single-file bundle → gzip.
  task_manager.py   → TASK.md lifecycle management.
  git_init.sh       → One-shot repo init + GitHub push.

.claude/
  settings.json     → MCP config + allowed bash commands. Edit via `claude mcp` commands.
  bootstrap.md      → This file.

.github/
  workflows/ci.yml  → Lint → Verify → Edge build → Auto-tag on main push.
```

**Rules:**
- `core/` — edit carefully, always run verify after
- `personas/` — one file = one persona, do not merge
- `edge_build/` — never commit, always regenerate
- `.hive/` — never commit (SQLite DB, task JSON, runtime state)
- `.env` — never commit (use `.env.example` as template)

---

## 7. Security Rules (Non-Negotiable)

```
NEVER hardcode secrets               → always os.environ.get()
NEVER commit .env or .hive/          → both in .gitignore
ALL diffs > 10 lines → Sentinel first → iron_gate_check() blocks automatically
Run hive_aegis before security code  → must output SHIP, not HOLD
Iron Gate fires on every Forge write → not a prompt rule, it's code
```

Secret patterns that trigger an immediate block:
- `api_key = "..."` or `token = "..."` with real values
- `sk-` prefixed strings
- `ghp_` prefixed strings

If Iron Gate blocks — do not bypass. Find and remove the secret, then retry.

---

## 8. Git Workflow

```bash
# Every feature
git checkout -b feat/persona-or-scope-description

# Before every commit — both must pass
python scripts/lint.py --no-info    # zero errors required
python scripts/verify.py            # all checks required

# Stage selectively — never git add . or git add -A
git add path/to/file1.py path/to/file2.py

# Commit format: type(scope): description
# Types: feat | fix | sec | perf | docs | test | refactor
git commit -m "feat(forge): add streaming response support"

# Push and open PR
git push origin feat/...
# CI runs: lint → verify → edge build → auto-tag on merge to main
```

**Never force-push to main. Never commit directly to main.**

---

## 9. Versioning

```bash
python scripts/version.py show              # current version
python scripts/version.py bump patch        # 0.1.0 → 0.1.1  (bug fix)
python scripts/version.py bump minor        # 0.1.0 → 0.2.0  (new feature)
python scripts/version.py bump major        # 0.1.0 → 1.0.0  (breaking change)
python scripts/version.py bump patch --tag  # bump + create git tag
python scripts/version.py history           # show all bumps
python scripts/version.py rollback 0.1.0    # revert VERSION file
```

Changelog is auto-generated from git commit messages at bump time.
CI auto-creates a GitHub release tag on every main push where VERSION has changed.

---

## 10. Task Management

```bash
python scripts/task_manager.py list                         # all tasks
python scripts/task_manager.py list forge                   # forge tasks only
python scripts/task_manager.py add forge "description" HIGH # add task
python scripts/task_manager.py start T-001                  # mark active
python scripts/task_manager.py done  T-001                  # mark complete
python scripts/task_manager.py status                       # persona summary
```

TASK.md is auto-regenerated from `.hive/tasks.json` — never edit TASK.md directly.

---

## 11. Edge Build

```bash
python scripts/edge_build.py --profile standard --validate
# Outputs: edge_build/hive_edge_standard.py  (~48KB minified)
#          edge_build/hive_edge_standard.py.gz (~15KB gzip, 77% reduction)

python scripts/edge_build.py --profile minimal --validate
# Outputs: Forge + Sentinel + Debug only (~10KB gzip)

python scripts/edge_build.py --all --dry-run   # preview sizes, no write
```

The edge bundle is a single valid Python file — deployable anywhere Python 3.11+ exists with just `pip install litellm`.

---

## 12. Memory & Learning

```bash
# In CLI
/rate +          # rate last response positively
/rate -          # rate last response negatively
/learn           # Coda extracts rules from top-rated interactions
/search query    # HNSW semantic search across all memory
/history         # recent sessions from SQLite
/stats           # DB + learning statistics
/resume forge    # reload Forge's conversation history
```

Run `/learn` weekly. Learned rules are injected into persona system prompts on next startup — HIVE improves from your usage patterns without any retraining.

---

## 13. MCP Tools (15 tools — available in Claude Code after registration)

```
hive_oracle(task)               → RPI loop: Research → Plan → Brief
hive_forge(brief)               → Code generation with always-on secret gate
hive_sentinel(file_path)        → Security review: secrets, vulns, Iron Gate
hive_heal(file_path)            → Auto-fix broken Python (max 3 attempts)
hive_muse(prompt)               → 3 rewrites: Precise / Constrained / Creative
hive_coda_compress(input)       → Compress to anchor (decisions + constraints)
hive_coda_verify(session_id)    → Check assertions for contradictions
hive_aegis(file_path)           → Red team: risk score + SHIP/HOLD/REDESIGN
hive_aegis_prompt(persona_name) → Red team a persona's system prompt
hive_apis_test(url)             → Generate Playwright UI test suite
hive_apis_crawl(url)            → Generate doc crawler script
hive_pipeline(task)             → Full Oracle→Forge→Sentinel+Aegis run
hive_memory_search(query)       → HNSW semantic search across all sessions
hive_memory_stats()             → Sessions, turns, rules, ratings summary
hive_rate(direction)            → Rate last interaction: "+" or "-"
```

---

## 14. Current Status

```
Version:     0.1.0
Personas:    8/8 implemented and verified
Verification: all checks passing
MCP tools:   15/15 registered
CI:          GitHub Actions (lint → verify → edge build → auto-tag)
Repo:        https://github.com/cyberdad247/hive-engine
Model:       claude-sonnet-4-6 (tier 2 default)
```

**Backlog (pick up from TASK.md):**
- T-001 `[LOW]`  Forge: async streaming responses
- T-002 `[HIGH]` Aegis: full red-team audit of all system prompts
- T-003 `[MED]`  Forge: GitHub Actions matrix testing

---

## 15. Definition of Done

A task is **done** when all of the following are true:

```
☐  python scripts/verify.py      → all checks passing ✅
☐  python scripts/lint.py        → 0 errors
☐  git diff --staged reviewed    → no secrets, no debug prints
☐  TASK.md updated               → python scripts/task_manager.py done T-XXX
☐  CHANGELOG entry exists        → python scripts/version.py bump patch
☐  Commit message follows format → type(scope): description
```

If any box is unchecked — the task is not done.

---

*🐝 HIVE v0.1.0 — Inspira Persona Engine | github.com/cyberdad247/hive-engine*
