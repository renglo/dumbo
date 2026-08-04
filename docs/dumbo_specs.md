# Dumbo harness — design notes

## Control plane

One LangGraph for all agents:

```
START → load_context → persist → call_llm ⇄ execute_tool → grounding_gate → END
```

Agents are `dumbo_profiles` documents (identity + tool_allowlist + write_tools + flags).

## Persistence (no Postgres checkpointer)

- Session key: `entity_type|entity_id|thread`
- Each inbound run: `create_turn` then append events
- Event types: `user_message`, `assistant_message`, `tool_call`, `tool_result`, `dumbo_approval`, `dumbo_stream`
- Cross-turn history: `Sessions.get_recent_chat_events` (windowed; see below)

## Session history window

Configured via `dumbo_config`:

- **`max_history_turns`** (default 20) — only the last N turn documents are scanned
- **`max_history_messages`** (default 40) — only user/assistant text kept for the prompt
- Newest turns are walked first; parsing stops once enough messages are collected
- `SessionController.list_turns` still caps at 50 turns server-side

Within the current turn, full tool call/result messages remain in graph state.

## Skills (JIT playbooks)

Ring: `dumbo_skills`. On each LLM call, trigger keywords in the user message select up to **`max_loaded_skills`** playbooks (default 2). Matched `instructions` are injected as a second system block after `profile.identity`.

See [`dumbo_skills_examples.md`](dumbo_skills_examples.md) for sample documents.

## HITL

Write path proposes into `dumbo_approvals` and returns `proposed_pending_approval` to the model. Execution happens only after user OK (gateway shortcut before the graph).

## Model

Default model comes from singleton `dumbo_config.model`. Profiles may override.
