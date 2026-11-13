"""LlmController facade. Returns OpenAI-shaped choices for the Dumbo graph."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from renglo.llm import LlmController
from renglo.llm.types import BLOCK_TEXT, BLOCK_TOOL_CALL, BLOCK_TOOL_RESULT


class Models:
    """Thin plane adapter. Model id comes from dumbo_config / profile, not a hard-coded mini."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        model: str = "gpt-4.1",
        temperature: float = 0.0,
        portfolio: str = "",
        org: str = "",
        agent_id: str = "",
        llm: Any = None,
    ) -> None:
        self.config = config or {}
        self._model = model
        self._temperature = temperature
        self.portfolio = str(portfolio or "")
        self.org = str(org or "")
        self.agent_id = str(agent_id or "")
        self._llm = llm if llm is not None else LlmController(config=self.config)

    @property
    def model(self) -> str:
        return self._model

    def set_model(self, model: str) -> None:
        if model:
            self._model = model

    def complete(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return OpenAI-shaped ``{"choices":[{"message":{...}}]}`` including ``tool_calls``.
        """
        try:
            provider_options: Dict[str, Any] = {
                "temperature": float(self._temperature if temperature is None else temperature),
            }
            if tool_choice:
                provider_options["tool_choice"] = tool_choice
            kwargs: Dict[str, Any] = {
                "messages": openai_messages_to_canonical(messages),
                "model": model or self._model,
                "provider_options": provider_options,
                "context": self._usage_context(),
            }
            canonical_tools = openai_tools_to_canonical(tools)
            if canonical_tools:
                kwargs["tools"] = canonical_tools
            result = self._llm.generate(**kwargs)
            if not result.get("success"):
                error = result.get("error") or "generate failed"
                return _assistant_choice(f"LLM error: {error}")
            return {
                "choices": [
                    {
                        "message": canonical_output_to_openai_message(
                            result.get("output") or {}
                        )
                    }
                ]
            }
        except Exception as exc:
            print(f"Error running LLM call: {exc}")
            return _assistant_choice(f"LLM error: {exc}")

    def _usage_context(self) -> Dict[str, str]:
        context = {"extension_id": "dumbo"}
        if self.portfolio:
            context["portfolio_id"] = self.portfolio
        if self.org:
            context["org_id"] = self.org
        if self.agent_id:
            context["agent_id"] = self.agent_id
        return context


def openai_tools_to_canonical(tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = str(fn.get("name") or tool.get("name") or "").strip()
        if not name:
            continue
        parameters = fn.get("parameters") or tool.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {"type": "object", "properties": {}}
        row: Dict[str, Any] = {"name": name, "parameters": parameters}
        description = str(fn.get("description") or tool.get("description") or "")
        if description:
            row["description"] = description
        out.append(row)
    return out


def openai_messages_to_canonical(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role == "tool":
            if isinstance(content, list):
                out.append({"role": "tool", "content": content})
                continue
            out.append(
                {
                    "role": "tool",
                    "content": [
                        {
                            "type": BLOCK_TOOL_RESULT,
                            "tool_call_id": str(message.get("tool_call_id") or ""),
                            "text": str(content or ""),
                        }
                    ],
                }
            )
            continue
        blocks: List[Dict[str, Any]] = []
        if isinstance(content, list):
            blocks.extend(item for item in content if isinstance(item, dict))
        elif isinstance(content, str) and content:
            blocks.append({"type": BLOCK_TEXT, "text": content})
        for tool_call in message.get("tool_calls") or []:
            if not isinstance(tool_call, dict):
                continue
            fn = tool_call.get("function") or {}
            blocks.append(
                {
                    "type": BLOCK_TOOL_CALL,
                    "id": str(tool_call.get("id") or ""),
                    "name": str(fn.get("name") or ""),
                    "arguments": _parse_arguments(fn.get("arguments")),
                }
            )
        if not blocks:
            blocks = [{"type": BLOCK_TEXT, "text": ""}]
        out.append({"role": role, "content": blocks})
    return out


def canonical_output_to_openai_message(output: Dict[str, Any]) -> Dict[str, Any]:
    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    for block in output.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == BLOCK_TEXT:
            text_parts.append(str(block.get("text") or ""))
            continue
        if block.get("type") == BLOCK_TOOL_CALL:
            args = block.get("arguments")
            if isinstance(args, dict):
                arg_str = json.dumps(args)
            elif isinstance(args, str) and args:
                arg_str = args
            else:
                arg_str = "{}"
            tool_calls.append(
                {
                    "id": str(block.get("id") or ""),
                    "type": "function",
                    "function": {
                        "name": str(block.get("name") or ""),
                        "arguments": arg_str,
                    },
                }
            )
    if not (output.get("content") or []) and output.get("text"):
        text_parts.append(str(output.get("text") or ""))
    row: Dict[str, Any] = {"role": "assistant", "content": "".join(text_parts)}
    if tool_calls:
        row["tool_calls"] = tool_calls
    return row


def _parse_arguments(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _assistant_choice(content: str) -> Dict[str, Any]:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}
