# DUMBO extension

Dumbo is a **flat LangGraph smart-model agent harness** for Renglo. One shared ReAct graph is parameterized by pure-data **profiles** (`identity` + `tool_allowlist`). Continuity uses Renglo **session turns** (not Postgres checkpoints). Write tools can require **HITL** via `dumbo_approvals`.

The implementation lives under `package/` as the installable Python module **`dumbo-mod`**.

## What it provides

| Piece | Role |
|--------|------|
| **`GenericAgent`** | Scheduler entry: loads config/profile/tools, handles HITL shortcuts, runs the graph |
| **Graph** | `load_context → persist → call_llm ⇄ execute_tool → grounding_gate` |
| **`Sessions`** | Turn ledger on DynamoDB (`DYNAMODB_SESSION_TABLE`) — checkpoint alternative |
| **`Tools`** | Loads `schd_tools`, filters by profile allowlist, dispatches via `SchdController` |
| **`Approvals`** | Propose / OK / NO HITL for write tools |
| **`ConfigStore`** | Singleton `dumbo_config` (model selection, limits, global approval tools) |
| **`Profiles`** | `dumbo_profiles` documents (allowlist, write_tools, supervisor/delegatable) |
| **`Skills`** | `dumbo_skills` JIT playbooks (trigger match → inject into prompt) |
| **UI** | Chat, config singleton, **Setup** (profiles/skills/gates), **Memory** (summaries/beliefs/approvals) |

## Install

From `extensions/dumbo/package/`:

```bash
pip install -e .
```

Python **3.12+**. Dependencies include **`langgraph`** and **`openai`**; platform integration expects **`renglo`**.

Upload blueprints:

```bash
python installer/upload_blueprints.py <env> --aws-profile <profile> --aws-region <region>
```

Add `dumbo` to console `VITE_EXTENSIONS`, install the package on the API host, then use **Install** on the Dumbo marketplace card (runs `dumbo/dumbo_onboardings`).

## Configuration

Env (same as CLAW/LGX):

- **`OPENAI_API_KEY`** — required for LLM calls
- **`DYNAMODB_SESSION_TABLE`** — session ledger (`<namespace>_session`)
- **`WEBSOCKET_CONNECTIONS`** — streaming when `connectionId` is present

### Singleton ring: `dumbo_config`

Created on onboarding (`_id` = `00000000-0000-0000-0000-000000000000`). Edit to pick the smart model:

| Field | Default | Notes |
|--------|---------|--------|
| `model` | `gpt-4.1` | Strong model required for flat tool selection |
| `temperature` | `0` | |
| `recursion_limit` | `40` | LangGraph safety |
| `default_agent_id` | `generalist` | |
| `max_history_messages` | `40` | Max user/assistant messages in prompt |
| `max_history_turns` | `20` | Max turn docs scanned (newest first) |
| `max_loaded_skills` | `2` | Max skill playbooks injected per turn |
| `approval_tools` | `[]` | Global HITL tool keys |
| `grounding_enabled` | `true` | |
| `max_grounding_retries` | `1` | |

Per-profile `model` / `recursion_limit` on `dumbo_profiles` override the singleton when set.

## HITL

A tool requires approval when:

1. Its `schd_tools.init` JSON has `"requires_approval": true`, or
2. Its key is listed in the profile’s `write_tools`, or
3. Its key is listed in `dumbo_config.approval_tools`

Proposed tools are stored in `dumbo_approvals`. The user replies:

- `OK` / `YES` / `CONFIRM` — approve latest pending
- `NO` / `REJECT` — reject latest
- `OK <approval_id>` / `approve:<id>` — approve a specific proposal

## Profiles & allowlists

Create documents in `dumbo_profiles`. `tool_allowlist` of `["*"]` (or `*`) binds all `schd_tools` (except the agent itself). Narrow lists keep large catalogs manageable.

Supervisor profiles get `delegate_to_agent` when other `delegatable` profiles exist (in-process, depth-1).

## Skills (JIT playbooks)

Documents in `dumbo_skills` inject extra system instructions when **trigger** keywords appear in the user message. They are **not** tools — see [`docs/dumbo_skills_examples.md`](docs/dumbo_skills_examples.md).

Onboarding seeds six example skills from `seed/dumbo_skills_examples.json` (skips existing keys).

## Demo tools (live public APIs)

Three **schd_tools** handlers call public APIs so the agent can answer with data outside its training cutoff (no API keys):

| Tool key | Handler | API |
|----------|---------|-----|
| `fetch_hacker_news` | `dumbo/fetch_hacker_news` | Hacker News Firebase |
| `fetch_wikipedia_summary` | `dumbo/fetch_wikipedia_summary` | Wikipedia REST |
| `fetch_exchange_rates` | `dumbo/fetch_exchange_rates` | Frankfurter (ECB rates) |

Registered per org in `schd_tools` (via onboarding or Schd UI). The active **`dumbo_profiles`** document for that org supplies **`tool_allowlist`**: `["*"]` binds every tool in the org (except `dumbo_agent`); a explicit list binds only those keys.

**Already onboarded at `_all` only?** Re-seed for your org: `POST /_schd/run/dumbo/seed_demo_tools` with `{"portfolio":"<id>","org":"<your-org>"}`.

Example chat prompts: *“What’s trending on Hacker News?”*, *“Summarize Wikipedia on LangGraph”*, *“USD to EUR rate today?”*

## Blueprints

| Ring | Purpose |
|------|---------|
| `dumbo_config` | Singleton settings (model, …) |
| `dumbo_profiles` | Agent-as-data |
| `dumbo_approvals` | HITL proposals |
| `dumbo_skills` | JIT playbooks (trigger → prompt injection) |
| `dumbo_summaries` | Episodic digests |
| `dumbo_beliefs` | Long-term facts |
| `dumbo_gates` | Optional grounding policies |

## Package layout

```
extensions/dumbo/
├── README.md
├── blueprints/
├── installer/
├── docs/
├── ui/                      # console chat + onboarding
└── package/
    ├── pyproject.toml       # dumbo-mod
    └── dumbo/handlers/      # GenericAgent, sessions, tools, approvals, …
```

## License

MIT — see `LICENSE.txt`.
