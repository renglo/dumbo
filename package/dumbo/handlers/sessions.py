from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from .class_prototypes import SessionEvent


SESSION_KEY_SEP = "|"

ROLL_EVENT_TYPES = frozenset(
    {
        "user_message",
        "assistant_message",
        "tool_call",
        "tool_result",
        "dumbo_event",
        "dumbo_approval",
        "channel_delivery",
    }
)

PROMPT_SKIP_TYPES = frozenset(
    {
        "dumbo_stream",
        "dumbo_signal",
    }
)

CHAT_EVENT_TYPES = frozenset({"user_message", "assistant_message"})
HISTORY_EVENT_TYPES = frozenset({"user_message", "assistant_message", "channel_delivery"})


def format_session_key(entity_type: str, entity_id: str, thread_id: str) -> str:
    return SESSION_KEY_SEP.join([entity_type, entity_id, thread_id])


def _sanitize_for_dynamo(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_dynamo(v) for v in obj]
    if isinstance(obj, float):
        return str(obj)
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


class Sessions:
    """Session ledger aligned with ``SessionController`` turns (checkpoint alternative)."""

    def __init__(
        self,
        session_controller: Any,
        portfolio: str,
        org: str,
        entity_type: str,
        entity_id: str,
        thread_id: str,
    ) -> None:
        self._ssc = session_controller
        self._portfolio = portfolio
        self._org = org
        self._entity_type = entity_type
        self._entity_id = entity_id
        self._thread_id = thread_id
        self.session_id = format_session_key(entity_type, entity_id, thread_id)
        self._active_turn_id: str | None = None

    def create_turn(self, context_payload: dict[str, Any], events: Optional[list] = None) -> str:
        ctx = dict(context_payload)
        if "public_user" not in ctx:
            ctx["public_user"] = False
        payload = {"context": ctx, "events": events or []}
        res = self._ssc.create_turn(
            self._portfolio,
            self._org,
            self._entity_type,
            self._entity_id,
            self._thread_id,
            payload,
        )
        if not res.get("success"):
            raise RuntimeError(res.get("message", "create_turn failed"))
        doc = res.get("document") or {}
        turn_id = str(doc.get("_id", ""))
        self._active_turn_id = turn_id
        return turn_id

    def get_active_turn_id(self) -> Optional[str]:
        return self._active_turn_id

    def update_turn(self, turn_id: str, update: dict[str, Any], call_id: Any = False) -> dict[str, Any]:
        return self._ssc.update_turn(
            self._portfolio,
            self._org,
            self._entity_type,
            self._entity_id,
            self._thread_id,
            turn_id,
            update,
            call_id=call_id,
        )

    def _base_meta(self, event: SessionEvent) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "event_id": event.event_id,
            "session_id": event.session_id,
            "timestamp": event.timestamp.isoformat(),
        }
        if event.metadata:
            meta.update(event.metadata)
        return meta

    def _roll_role(self, event_type: str) -> str:
        if event_type == "user_message":
            return "user"
        if event_type == "assistant_message":
            return "assistant"
        if event_type in ("tool_call", "tool_result"):
            return "tool"
        return "system"

    def _event_to_message(self, event: SessionEvent) -> dict[str, Any]:
        et = event.event_type
        meta = self._base_meta(event)

        if et in ("user_message", "assistant_message"):
            text = event.payload.get("text")
            if text is None:
                text = event.payload.get("message", "")
            row = {
                "_type": et,
                "_out": {"role": self._roll_role(et), "content": str(text)},
                "_meta": _sanitize_for_dynamo(meta),
            }
            return _sanitize_for_dynamo(row)

        if et == "channel_delivery":
            body = _sanitize_for_dynamo(dict(event.payload))
            row = {
                "_type": et,
                "_out": {
                    "role": "system",
                    "content": body,
                },
                "_meta": _sanitize_for_dynamo(meta),
            }
            return _sanitize_for_dynamo(row)

        body = _sanitize_for_dynamo(dict(event.payload))
        row = {
            "_type": et,
            "_out": {
                "role": self._roll_role(et),
                "content": body,
            },
            "_meta": _sanitize_for_dynamo(meta),
        }
        return _sanitize_for_dynamo(row)

    def _parse_timestamp(self, raw: Any) -> datetime:
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return datetime.utcnow()
        return datetime.utcnow()

    def _message_to_event(self, session_id: str, msg: dict[str, Any]) -> Optional[SessionEvent]:
        et = msg.get("_type")
        if not et or not isinstance(et, str):
            return None

        meta = msg.get("_meta") if isinstance(msg.get("_meta"), dict) else {}
        out = msg.get("_out")
        if not isinstance(out, dict):
            out = {}

        event_id = str(meta.get("event_id") or uuid.uuid4())
        sid = str(meta.get("session_id") or session_id)
        ts = self._parse_timestamp(meta.get("timestamp"))
        extra_meta = {k: v for k, v in meta.items() if k not in ("event_id", "session_id", "timestamp")}

        if et in ("user_message", "assistant_message"):
            content = out.get("content")
            payload = {"text": content if isinstance(content, str) else json.dumps(content, default=str)}
            return SessionEvent(
                event_id=event_id,
                session_id=sid,
                event_type=et,
                timestamp=ts,
                payload=payload,
                metadata=extra_meta,
            )

        if et == "channel_delivery":
            content = out.get("content")
            if isinstance(content, dict):
                payload = dict(content)
            else:
                payload = {"status": "unknown", "detail": content}
            return SessionEvent(
                event_id=event_id,
                session_id=sid,
                event_type=et,
                timestamp=ts,
                payload=payload,
                metadata=extra_meta,
            )

        content = out.get("content")
        if isinstance(content, dict):
            payload = dict(content)
        else:
            payload = dict(out) if out else {"text": str(content)}
        return SessionEvent(
            event_id=event_id,
            session_id=sid,
            event_type=et,
            timestamp=ts,
            payload=payload,
            metadata=extra_meta,
        )

    def append_event(self, event: SessionEvent) -> None:
        turn_id = self.get_active_turn_id()
        if not turn_id:
            raise RuntimeError("No active turn; call create_turn first")
        self.update_turn(turn_id, self._event_to_message(event), call_id=False)

    def get_events(
        self,
        session_id: str,
        limit: Optional[int] = None,
        since_event_id: Optional[str] = None,
    ) -> list[SessionEvent]:
        if session_id != self.session_id:
            raise ValueError("session_id mismatch")
        res = self._ssc.list_turns(
            self._portfolio,
            self._org,
            self._entity_type,
            self._entity_id,
            self._thread_id,
            False,
        )
        if not res.get("success"):
            return []
        events: list[SessionEvent] = []
        for turn in res.get("items", []):
            for m in turn.get("events") or []:
                ev = self._message_to_event(session_id, m)
                if ev:
                    events.append(ev)
        if since_event_id:
            try:
                idx = next(i for i, e in enumerate(events) if e.event_id == since_event_id)
                events = events[idx + 1 :]
            except StopIteration:
                pass
        if limit is not None:
            events = events[-limit:]
        return events

    def get_recent_chat_events(
        self,
        session_id: str,
        *,
        max_messages: int = 40,
        max_turns: int = 20,
    ) -> list[SessionEvent]:
        """
        Load only the tail of the session ledger for prompt history.

        Unlike ``get_events``, this:
        - considers only the last ``max_turns`` turn documents (SessionController
          already caps the query at 50 turns)
        - parses only ``user_message`` / ``assistant_message`` events
        - walks newest turns first and stops once enough messages are collected
        """
        if session_id != self.session_id:
            raise ValueError("session_id mismatch")

        res = self._ssc.list_turns(
            self._portfolio,
            self._org,
            self._entity_type,
            self._entity_id,
            self._thread_id,
            False,
        )
        if not res.get("success"):
            return []

        turns = res.get("items", []) or []
        if max_turns and max_turns > 0:
            turns = turns[-max_turns:]

        collected: list[SessionEvent] = []
        for turn in reversed(turns):
            batch: list[SessionEvent] = []
            for m in turn.get("events") or []:
                ev = self._message_to_event(session_id, m)
                if not ev or ev.event_type not in HISTORY_EVENT_TYPES:
                    continue
                if ev.event_type in PROMPT_SKIP_TYPES:
                    continue
                if ev.event_type == "channel_delivery":
                    batch.append(ev)
                    continue
                text = ev.payload.get("text") or ev.payload.get("message") or ""
                if str(text).strip():
                    batch.append(ev)
            if batch:
                collected = batch + collected
            if len(collected) >= max_messages:
                break

        return collected[-max_messages:]
