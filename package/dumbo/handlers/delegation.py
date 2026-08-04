"""In-process depth-1 sub-agent loop (no nested LangGraph / checkpointer)."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from .class_prototypes import AgentProfile, ToolDefinition
from .models import Models
from .tools import Tools

_logger = logging.getLogger(__name__)

MAX_SUBAGENT_STEPS = 6


def run_subagent_loop(
    *,
    profile: AgentProfile,
    task: str,
    tools: list[ToolDefinition],
    models: Models,
    execute_tool: Callable[[str, dict[str, Any], Optional[str]], dict[str, Any]],
    max_steps: int = MAX_SUBAGENT_STEPS,
) -> str:
    """
    Bounded ReAct loop for a delegatable profile.

    ``execute_tool(name, args, call_id) -> {success, result, error, proposed?}``
    """
    oa_tools = Tools.tool_definitions_to_openai(tools)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": profile.identity},
        {
            "role": "user",
            "content": (
                f"You are running as sub-agent '{profile.name}' ({profile.id}). "
                f"Complete this task and return a concise final answer.\n\nTask:\n{task}"
            ),
        },
    ]

    for _step in range(max_steps):
        resp = models.complete(
            messages,
            tools=oa_tools or None,
            tool_choice="auto",
            model=profile.model or models.model,
        )
        msg = (resp.get("choices") or [{}])[0].get("message") or {}
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            return (content or "").strip() or f"(sub-agent {profile.id} finished with empty reply)"

        assistant_row: dict[str, Any] = {"role": "assistant", "content": content or ""}
        assistant_row["tool_calls"] = tool_calls
        messages.append(assistant_row)

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except Exception:
                args = {}
            if name == "delegate_to_agent":
                result = {
                    "success": False,
                    "error": "Nested delegation is not allowed (depth-1 invariant).",
                }
            else:
                result = execute_tool(name, args, tc.get("id"))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or name,
                    "content": json.dumps(result, default=str)[:12000],
                }
            )

    return f"(sub-agent {profile.id} stopped after {max_steps} steps without a final answer)"
