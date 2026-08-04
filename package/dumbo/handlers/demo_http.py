"""Small HTTP helpers for Dumbo demo tools (stdlib only, no API keys)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def fetch_json(url: str, *, timeout: float = 12.0) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "dumbo-demo-tool/1.0 (renglo dev)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def tool_error(message: str, *, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "success": False,
        "action": action,
        "message": message,
        "input": payload or {},
        "output": {"error": message},
    }


def tool_ok(action: str, payload: dict[str, Any], output: Any) -> dict[str, Any]:
    return {
        "success": True,
        "action": action,
        "input": payload,
        "output": output,
    }
