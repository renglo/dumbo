"""Rebuild a model transcript from session events, one tool message per call id."""

from __future__ import annotations

import json
from typing import Any

from .class_prototypes import SessionEvent
from .tools import Tools


def pair_timeline(events: list[SessionEvent]) -> list[dict[str, Any]]:
    """User and assistant text, plus one tool call and its latest result.

    The pair is placed where the latest result sits, so a line the agent
    wrote while the call was still running stays before the result.
    """
    latest = _latest_results(events)
    anchors = _anchors(events, latest)
    calls = _calls(events)
    emitted: set[str] = set()
    messages: list[dict[str, Any]] = []
    for event in events:
        if event.event_type == "channel_delivery":
            note = _failed_delivery(event)
            if note:
                messages.append(note)
            continue
        if event.event_type in ("tool_call", "tool_result"):
            call_id = str(event.payload.get("call_id") or "").strip()
            call = calls.get(call_id) if call_id else None
            if (
                call is not None
                and call_id not in emitted
                and anchors.get(call_id) == event.event_id
            ):
                emitted.add(call_id)
                messages.extend(_tool_pair(call, latest.get(call_id)))
            continue
        text = event.payload.get("text") or event.payload.get("message") or ""
        if not str(text).strip():
            continue
        role = "user" if event.event_type == "user_message" else "assistant"
        messages.append({"role": role, "content": str(text)})
    return messages


def _calls(events: list[SessionEvent]) -> dict[str, SessionEvent]:
    found: dict[str, SessionEvent] = {}
    for event in events:
        if event.event_type != "tool_call":
            continue
        call_id = str(event.payload.get("call_id") or "").strip()
        if call_id and call_id not in found:
            found[call_id] = event
    return found


def _anchors(events: list[SessionEvent], latest: dict[str, SessionEvent]) -> dict[str, str]:
    """Event id where the tool pair is inserted. The latest result wins."""
    anchors: dict[str, str] = {}
    for event in events:
        if event.event_type != "tool_call":
            continue
        call_id = str(event.payload.get("call_id") or "").strip()
        if call_id:
            anchors.setdefault(call_id, event.event_id)
    for call_id, event in latest.items():
        anchors[call_id] = event.event_id
    return anchors


def _latest_results(events: list[SessionEvent]) -> dict[str, SessionEvent]:
    latest: dict[str, SessionEvent] = {}
    for event in events:
        if event.event_type != "tool_result":
            continue
        call_id = str(event.payload.get("call_id") or "").strip()
        if not call_id:
            continue
        previous = latest.get(call_id)
        if previous is None or _is_running(previous) or not _is_running(event):
            latest[call_id] = event
    return latest


def _is_running(event: SessionEvent) -> bool:
    result = event.payload.get("result")
    return isinstance(result, dict) and str(result.get("status") or "") == "running"


def _tool_pair(call: SessionEvent, result: SessionEvent | None) -> list[dict[str, Any]]:
    call_id = str(call.payload.get("call_id") or "")
    # Session stores the schd key (extension/handler). The model API rejects the slash.
    name = Tools.openai_function_name(str(call.payload.get("tool") or "tool"))
    arguments = call.payload.get("arguments") or {}
    if not isinstance(arguments, str):
        try:
            arguments = json.dumps(arguments, default=str)
        except (TypeError, ValueError):
            arguments = "{}"
    content = {
        "success": False if result is None else result.payload.get("success", True),
        "output": {} if result is None else result.payload.get("result"),
        "error": None if result is None else result.payload.get("error"),
    }
    try:
        rendered = json.dumps(content, default=str)
    except (TypeError, ValueError):
        rendered = str(content)
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call_id,
            "content": rendered[:12000],
        },
    ]


def _failed_delivery(event: SessionEvent) -> dict[str, Any] | None:
    status = str(event.payload.get("status") or "")
    if status != "failed":
        return None
    channel = str(event.payload.get("channel") or "channel")
    err = (
        event.payload.get("provider_error")
        or event.payload.get("error")
        or event.payload.get("provider_status")
        or "unknown error"
    )
    if isinstance(err, (dict, list)):
        err = json.dumps(err, default=str)[:400]
    return {
        "role": "system",
        "content": (
            f"[channel_delivery failed on {channel}] "
            f"The previous assistant reply was not delivered: {err}"
        ),
    }
