"""Models.complete maps plane tool_call blocks into OpenAI-shaped choices."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = Path(__file__).resolve().parents[4] / "dev" / "renglo-lib"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(LIB))

from dumbo.lib.models import Models  # noqa: E402


class _FakeLlm:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class ModelsFacadeTests(unittest.TestCase):
    def test_plane_tool_call_becomes_openai_tool_calls(self) -> None:
        llm = _FakeLlm(
            {
                "success": True,
                "output": {
                    "text": "",
                    "content": [
                        {
                            "type": "tool_call",
                            "id": "call_1",
                            "name": "arbitiumremediation_catalog_search",
                            "arguments": {"domain": "storage"},
                        }
                    ],
                },
            }
        )
        models = Models(config={}, model="us.anthropic.claude-sonnet-5-5", llm=llm)
        oa_tools = [
            {
                "type": "function",
                "function": {
                    "name": "arbitiumremediation_catalog_search",
                    "description": "Search the catalog",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        resp = models.complete(
            [{"role": "user", "content": "plan this"}],
            tools=oa_tools,
            tool_choice="auto",
        )
        msg = resp["choices"][0]["message"]
        self.assertEqual(msg["tool_calls"][0]["id"], "call_1")
        self.assertEqual(
            msg["tool_calls"][0]["function"]["name"],
            "arbitiumremediation_catalog_search",
        )
        self.assertEqual(
            json.loads(msg["tool_calls"][0]["function"]["arguments"]),
            {"domain": "storage"},
        )
        call = llm.calls[0]
        self.assertEqual(call["model"], "us.anthropic.claude-sonnet-5-5")
        self.assertNotIn("fallback", call)
        self.assertEqual(call["tools"][0]["name"], "arbitiumremediation_catalog_search")
        self.assertEqual(call["context"]["extension_id"], "dumbo")

    def test_generate_failure_becomes_assistant_text(self) -> None:
        llm = _FakeLlm({"success": False, "error": "Unknown model gpt-4.1"})
        models = Models(config={}, llm=llm)
        resp = models.complete([{"role": "user", "content": "hi"}])
        self.assertIn("Unknown model gpt-4.1", resp["choices"][0]["message"]["content"])
        self.assertNotIn("tool_calls", resp["choices"][0]["message"])


if __name__ == "__main__":
    unittest.main()
