"""OpenAI chat-completions adapter with tool-call support (smart-model default)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import OpenAI


class Models:
    """Thin OpenAI adapter. Model id is injected from ``dumbo_config`` (not hard-coded mini)."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        model: str = "gpt-4.1",
        temperature: float = 0.0,
    ) -> None:
        self.config = config or {}
        self._model = model
        self._temperature = temperature
        try:
            openai_key = self.config.get("OPENAI_API_KEY", "")
            self._client = OpenAI(api_key=openai_key) if openai_key else None
        except Exception as exc:
            print(f"Error initializing OpenAI client: {exc}")
            self._client = None

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
        if self._client is None:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "OpenAI client is not configured (missing OPENAI_API_KEY).",
                        }
                    }
                ]
            }

        try:
            params: Dict[str, Any] = {
                "model": model or self._model,
                "messages": messages,
                "temperature": float(self._temperature if temperature is None else temperature),
            }
            if tools:
                params["tools"] = tools
                params["tool_choice"] = tool_choice
            response = self._client.chat.completions.create(**params)
            msg = response.choices[0].message
            return {"choices": [{"message": self.completion_message_to_choice_dict(msg)}]}
        except Exception as exc:
            print(f"Error running LLM call: {exc}")
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": f"LLM error: {exc}",
                        }
                    }
                ]
            }

    @staticmethod
    def completion_message_to_choice_dict(msg: Any) -> dict[str, Any]:
        row: dict[str, Any] = {
            "role": getattr(msg, "role", "assistant"),
            "content": getattr(msg, "content", None) or "",
        }
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return row
        serialized = []
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            name = getattr(fn, "name", "") if fn is not None else ""
            arguments = getattr(fn, "arguments", "{}") if fn is not None else "{}"
            serialized.append(
                {
                    "id": getattr(tc, "id", None),
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            )
        row["tool_calls"] = serialized
        return row
