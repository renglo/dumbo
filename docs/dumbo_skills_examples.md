# Dumbo skill examples

Skills are **prompt playbooks** stored in the `dumbo_skills` ring. They are **not** executable tools — they inject instructions when trigger keywords appear in the user's message.

## How matching works

1. On each LLM call, Dumbo scans the inbound user text (case-insensitive substring match).
2. Each skill's `triggers` list is checked in ring load order.
3. At most **`dumbo_config.max_loaded_skills`** playbooks are injected (default **2**).
4. Skills with empty `profile_ids` apply to **all** profiles; otherwise the active profile id must be listed.

Injected block order in the prompt:

```
system: {profile.identity}          ← static
system: {matched skill playbooks}   ← JIT
system: {dynamic context}           ← time, pending approvals, delegation list
user/assistant history…
```

## Install examples

### Option A — onboarding (recommended)

Re-run or extend onboarding: `dumbo/dumbo_onboardings` seeds example skills from `seed/dumbo_skills_examples.json` (skips keys that already exist).

### Option B — manual ring documents

Create documents in **`dumbo_skills`** via the data console or API. Each document needs:

| Field | Required | Description |
|--------|----------|-------------|
| `key` | yes | Stable id (e.g. `weekly-review`) |
| `triggers` | yes | Keywords/phrases that activate the skill |
| `instructions` | yes | Playbook text injected into the system prompt |
| `tool_hints` | no | Suggested `schd_tools` keys (guidance only) |
| `profile_ids` | no | Limit to specific profile ids; empty = all |

---

## Example 1 — Weekly review

**Triggers:** `weekly review`, `week in review`, `retrospective`

```json
{
  "key": "weekly-review",
  "triggers": ["weekly review", "week in review", "retrospective", "what did we accomplish"],
  "instructions": "Run a concise weekly review:\n1. Summarize what was discussed or done this week.\n2. List open items and blockers.\n3. Propose 3 priorities for next week.\nKeep it scannable with bullets.",
  "tool_hints": [],
  "profile_ids": []
}
```

**Try in chat:** *"Can you run a weekly review of our thread?"*

---

## Example 2 — HITL write guidance

**Triggers:** `delete`, `send email`, `create`, `update`, `approve`

```json
{
  "key": "hitl-writes",
  "triggers": ["delete", "remove", "send email", "post", "create", "update", "approve", "write"],
  "instructions": "If a tool returns proposed_pending_approval, explain what will happen if approved and ask the user to reply OK or NO. Never claim completion until execution succeeded.",
  "tool_hints": [],
  "profile_ids": []
}
```

**Try in chat:** *"Create a new record for vendor Acme"* (when that tool is on `write_tools`)

---

## Example 3 — Research brief

```json
{
  "key": "research-brief",
  "triggers": ["research", "investigate", "look into", "summarize sources"],
  "instructions": "Produce a short research brief: restate the question, use read/search tools when available, give findings + confidence + gaps, end with next steps.",
  "tool_hints": [],
  "profile_ids": []
}
```

**Try in chat:** *"Research options for consolidating our SaaS spend"*

---

## Example 4 — Delegation (generalist only)

```json
{
  "key": "delegation",
  "triggers": ["delegate", "specialist", "hand off", "financial", "legal"],
  "instructions": "When a specialist fits better, call delegate_to_agent with agent_id and a clear task. Summarize the sub-agent answer for the user.",
  "tool_hints": ["delegate_to_agent"],
  "profile_ids": ["generalist"]
}
```

**Try in chat:** *"Delegate a financial audit of Q3 expenses to the specialist"*

---

## Example 5 — Capabilities / tool discovery

```json
{
  "key": "tool-discovery",
  "triggers": ["what can you do", "capabilities", "which tools", "help me with"],
  "instructions": "Explain capabilities at a high level with 3–5 example tasks. Mention HITL OK/NO for write tools when relevant.",
  "tool_hints": [],
  "profile_ids": []
}
```

**Try in chat:** *"What can you help me with?"*

---

## Example 6 — Incident triage

```json
{
  "key": "incident-triage",
  "triggers": ["incident", "outage", "down", "error spike", "sev", "on-call"],
  "instructions": "Triage like on-call: impact, scope, timeline, containment vs investigation, short update plan.",
  "tool_hints": [],
  "profile_ids": []
}
```

**Try in chat:** *"We have a SEV2 outage on the API gateway"*

---

## Tuning

| Config field | Default | Effect |
|--------------|---------|--------|
| `max_loaded_skills` | 2 | Cap playbooks per turn |
| `max_history_messages` | 40 | Chat messages in prompt |
| `max_history_turns` | 20 | Turn documents scanned (newest first) |

Full seed file: [`seed/dumbo_skills_examples.json`](../seed/dumbo_skills_examples.json)
