"""HITL approvals stored in ``dumbo_approvals`` (write tools propose; user confirms)."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Optional

_logger = logging.getLogger(__name__)

RING = "dumbo_approvals"

_APPROVE_WORDS = frozenset({"ok", "yes", "y", "approve", "confirm", "lgtm"})
_REJECT_WORDS = frozenset({"no", "n", "reject", "deny", "cancel"})


class Approvals:
    def __init__(
        self,
        data_controller: Any,
        portfolio: str,
        org: str,
        *,
        entity_type: str = "",
        entity_id: str = "",
        thread: str = "",
    ) -> None:
        self.DAC = data_controller
        self.portfolio = portfolio
        self.org = org
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.thread = thread

    def propose(
        self,
        *,
        tool_key: str,
        arguments: dict[str, Any],
        call_id: Optional[str],
        request_id: str,
        extension: str,
        handler: str,
        tool_init: dict[str, Any],
        rationale: str = "",
    ) -> dict[str, Any]:
        approval_id = str(uuid.uuid4())
        body = {
            "status": "proposed",
            "tool_key": tool_key,
            "arguments": arguments,
            "call_id": call_id or "",
            "request_id": request_id,
            "extension": extension,
            "handler": handler,
            "tool_init": tool_init or {},
            "rationale": rationale,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "thread": self.thread,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "resolved_at": "",
            "resolved_by": "",
            "result": {},
        }
        # Force stable id via post then put if needed — construct_post may ignore _id for non-singleton.
        # Prefer putting _id in payload; DataController may regenerate. Store returned id.
        response, _status = self.DAC.post_a_b(self.portfolio, self.org, RING, body)
        if not response.get("success"):
            raise RuntimeError(response.get("message", "Failed to create approval"))
        item = response.get("item") or response.get("document") or {}
        returned_id = str(item.get("_id") or approval_id)
        return {
            "approval_id": returned_id,
            "status": "proposed",
            "tool_key": tool_key,
            "arguments": arguments,
            "rationale": rationale,
        }

    def list_pending(self, limit: int = 20) -> list[dict[str, Any]]:
        res = self.DAC.get_a_b(self.portfolio, self.org, RING, limit=200)
        items = res.get("items", []) if res.get("success") else []
        pending = []
        for doc in items:
            if str(doc.get("status") or "") != "proposed":
                continue
            doc_entity = str(doc.get("entity_id") or "")
            if self.entity_id and doc_entity and doc_entity != self.entity_id:
                continue
            pending.append(doc)
        pending.sort(key=lambda d: str(d.get("created_at") or ""), reverse=True)
        return pending[:limit]

    def get(self, approval_id: str) -> Optional[dict[str, Any]]:
        res = self.DAC.get_a_b_c(self.portfolio, self.org, RING, approval_id)
        if res.get("success") is False or "_id" not in res:
            return None
        return res

    def _mark(
        self,
        approval_id: str,
        status: str,
        *,
        resolved_by: str = "",
        result: Any = None,
    ) -> dict[str, Any]:
        payload = {
            "status": status,
            "resolved_at": datetime.utcnow().isoformat() + "Z",
            "resolved_by": resolved_by or "",
            "result": result if result is not None else {},
        }
        response, _status = self.DAC.put_a_b_c(
            self.portfolio, self.org, RING, approval_id, payload
        )
        return response

    def resolve_and_execute(
        self,
        approval_id: str,
        *,
        decision: str,
        schd_controller: Any,
        resolved_by: str = "",
    ) -> dict[str, Any]:
        doc = self.get(approval_id)
        if not doc:
            return {"success": False, "error": f"Approval {approval_id} not found"}
        if str(doc.get("status")) != "proposed":
            return {
                "success": False,
                "error": f"Approval is not pending (status={doc.get('status')})",
            }

        if decision == "rejected":
            self._mark(approval_id, "rejected", resolved_by=resolved_by)
            return {
                "success": True,
                "decision": "rejected",
                "approval_id": approval_id,
                "tool_key": doc.get("tool_key"),
            }

        extension = str(doc.get("extension") or "").strip()
        handler = str(doc.get("handler") or "").strip()
        if not extension or not handler or not schd_controller:
            self._mark(
                approval_id,
                "failed",
                resolved_by=resolved_by,
                result={"error": "missing extension/handler"},
            )
            return {"success": False, "error": "Approval missing extension/handler"}

        args = doc.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        if not isinstance(args, dict):
            args = {}
        tool_init = doc.get("tool_init") or {}
        if isinstance(tool_init, str):
            try:
                tool_init = json.loads(tool_init) if tool_init.strip() not in ("", "_") else {}
            except Exception:
                tool_init = {}
        params = dict(args)
        params["_init"] = tool_init if isinstance(tool_init, dict) else {}
        params["_delegated"] = True
        params["_approval_id"] = approval_id

        out = schd_controller.handler_call(
            self.portfolio, self.org, extension, handler, params
        )
        ok = bool(out.get("success"))
        self._mark(
            approval_id,
            "approved" if ok else "failed",
            resolved_by=resolved_by,
            result=out.get("output") if ok else {"error": out.get("output")},
        )
        return {
            "success": ok,
            "decision": "approved",
            "approval_id": approval_id,
            "tool_key": doc.get("tool_key"),
            "output": out.get("output"),
            "error": None if ok else out.get("output"),
        }

    @staticmethod
    def parse_shortcut(text: str) -> Optional[dict[str, Any]]:
        """
        Parse HITL shortcuts from inbound user text.

        Bare ``OK`` / ``YES`` / ``NO`` are returned with ``_bare: True``; the caller
        must only act on those when a pending approval exists for this session.
        Messages with an explicit approval id always match regardless of pending state.
        """
        raw = (text or "").strip()
        if not raw:
            return None
        lowered = raw.lower().strip()

        m = re.match(r"^(ok|yes|approve|confirm)\s+([0-9a-f-]{8,})$", lowered)
        if m:
            return {"decision": "approved", "approval_id": m.group(2)}
        m = re.match(r"^(no|reject|deny)\s+([0-9a-f-]{8,})$", lowered)
        if m:
            return {"decision": "rejected", "approval_id": m.group(2)}
        m = re.match(r"^approve:([0-9a-f-]{8,})$", lowered)
        if m:
            return {"decision": "approved", "approval_id": m.group(1)}
        m = re.match(r"^reject:([0-9a-f-]{8,})$", lowered)
        if m:
            return {"decision": "rejected", "approval_id": m.group(1)}

        # Bare OK/YES/NO only apply when the user is responding to HITL (handled upstream).
        token = re.sub(r"[.!]+$", "", lowered).strip()
        if token in _APPROVE_WORDS:
            return {"decision": "approved", "_bare": True}
        if token in _REJECT_WORDS:
            return {"decision": "rejected", "_bare": True}
        return None
