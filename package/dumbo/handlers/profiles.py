"""Load AgentProfile documents from ``dumbo_profiles``."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .class_prototypes import AgentProfile

_logger = logging.getLogger(__name__)

RING = "dumbo_profiles"

DEFAULT_GENERALIST = AgentProfile(
    id="generalist",
    code="D-01",
    name="Dumbo Generalist",
    identity=(
        "You are Dumbo, a capable generalist agent running inside Renglo. "
        "Use tools when they improve accuracy — especially for live or external data "
        "(news, rates, Wikipedia). Prefer concise, actionable answers. "
        "When a tool returns status proposed_pending_approval, tell the user clearly "
        "what you proposed and ask them to reply OK to approve or NO to reject. "
        "Do not claim a write/side-effect completed until it was approved and executed. "
        "If you lack enough information, ask a focused clarifying question."
    ),
    tool_allowlist="all",
    write_tools=[],
    delegatable=False,
    supervisor=True,
    enabled=True,
)


class Profiles:
    def __init__(self, data_controller: Any, portfolio: str, org: str = "_all") -> None:
        self.DAC = data_controller
        self.portfolio = portfolio
        self.org = org
        self._by_id: dict[str, AgentProfile] = {}
        self.reload()

    @staticmethod
    def _contains_nested_list(raw: Any) -> bool:
        if not isinstance(raw, (list, tuple)):
            return False
        return any(isinstance(item, (list, tuple)) for item in raw)

    @staticmethod
    def normalize_tool_allowlist_for_storage(raw: Any) -> list[str]:
        """
        Flat list of tool keys for persistence. Wildcard is exactly ``["*"]``.
        Raises ``ValueError`` on nested lists (invalid blueprint/widget shape).
        """
        parsed = raw
        if isinstance(raw, str) and raw.strip() and raw.strip() != "_":
            try:
                parsed = json.loads(raw)
            except Exception:
                parts = [p.strip() for p in raw.split(",") if p.strip()]
                if not parts or "*" in parts:
                    return ["*"]
                return parts

        if parsed is None or parsed == "" or parsed == "_":
            return ["*"]
        if isinstance(parsed, list):
            if Profiles._contains_nested_list(parsed):
                raise ValueError(
                    "tool_allowlist must be a flat list of strings (e.g. [\"*\"]), not nested lists"
                )
            vals = [str(x).strip() for x in parsed if str(x).strip() and str(x).strip() != "_"]
            if not vals or "*" in vals:
                return ["*"]
            return vals
        token = str(parsed).strip()
        if token in ("*", "all"):
            return ["*"]
        return [token] if token else ["*"]

    def _parse_allowlist(self, raw: Any) -> list[str] | str:
        if raw is None or raw == "" or raw == "_":
            return "all"
        if isinstance(raw, list):
            if self._contains_nested_list(raw):
                _logger.warning(
                    "Invalid nested tool_allowlist %r — expected flat strings like [\"*\"]. "
                    "Binding all tools for this turn; fix the profile document in Setup.",
                    raw,
                )
                return "all"
            vals = [str(x).strip() for x in raw if str(x).strip() and str(x).strip() != "_"]
            if not vals or "*" in vals:
                return "all"
            return vals
        if isinstance(raw, str):
            s = raw.strip()
            if s in ("*", "all"):
                return "all"
            try:
                parsed = json.loads(s)
                return self._parse_allowlist(parsed)
            except Exception:
                parts = [p.strip() for p in s.split(",") if p.strip()]
                if not parts or "*" in parts:
                    return "all"
                return parts
        return "all"

    @staticmethod
    def allowlist_to_shortlist(allowlist: list[str] | str) -> list[str] | None:
        """``None`` means all tools; otherwise an explicit key list."""
        if allowlist == "all":
            return None
        if isinstance(allowlist, list):
            flat = [str(x).strip() for x in allowlist if str(x).strip()]
            if not flat or "*" in flat:
                return None
            return flat
        return None

    def _parse_str_list(self, raw: Any) -> list[str]:
        if isinstance(raw, list):
            if self._contains_nested_list(raw):
                _logger.warning("Invalid nested string list %r; ignoring nested entries", raw)
                raw = [x for x in raw if not isinstance(x, (list, tuple))]
            return [str(x).strip() for x in raw if str(x).strip()]
        if isinstance(raw, str) and raw.strip() and raw.strip() != "_":
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                pass
            return [p.strip() for p in raw.split(",") if p.strip()]
        return []

    def _doc_to_profile(self, doc: dict[str, Any]) -> Optional[AgentProfile]:
        pid = str(doc.get("id") or doc.get("key") or "").strip()
        if not pid:
            return None
        enabled_raw = doc.get("enabled", True)
        if isinstance(enabled_raw, str):
            enabled = enabled_raw.strip().lower() in ("1", "true", "yes", "on")
        else:
            enabled = bool(enabled_raw)
        if not enabled:
            return None

        recursion = doc.get("recursion_limit")
        try:
            recursion_limit = int(recursion) if recursion not in (None, "", "_") else None
        except (TypeError, ValueError):
            recursion_limit = None

        model = doc.get("model")
        model_str = str(model).strip() if model not in (None, "", "_") else None

        return AgentProfile(
            id=pid,
            code=str(doc.get("code") or "").strip() or pid,
            name=str(doc.get("name") or pid).strip(),
            identity=str(doc.get("identity") or DEFAULT_GENERALIST.identity),
            tool_allowlist=self._parse_allowlist(doc.get("tool_allowlist")),
            write_tools=self._parse_str_list(doc.get("write_tools")),
            delegatable=bool(doc.get("delegatable", False))
            if not isinstance(doc.get("delegatable"), str)
            else doc.get("delegatable", "").strip().lower() in ("1", "true", "yes", "on"),
            supervisor=bool(doc.get("supervisor", False))
            if not isinstance(doc.get("supervisor"), str)
            else doc.get("supervisor", "").strip().lower() in ("1", "true", "yes", "on"),
            enabled=True,
            recursion_limit=recursion_limit,
            model=model_str or None,
        )

    def reload(self) -> None:
        self._by_id = {}
        try:
            res = self.DAC.get_a_b(self.portfolio, self.org, RING, limit=200)
            items = res.get("items", []) if res.get("success") else []
            for doc in items:
                profile = self._doc_to_profile(doc)
                if profile:
                    self._by_id[profile.id] = profile
        except Exception as exc:
            _logger.warning("Failed to load dumbo_profiles: %s", exc)
        if "generalist" not in self._by_id:
            self._by_id["generalist"] = DEFAULT_GENERALIST

    def get(self, agent_id: Optional[str], default_id: str = "generalist") -> AgentProfile:
        if agent_id and agent_id in self._by_id:
            return self._by_id[agent_id]
        return self._by_id.get(default_id) or DEFAULT_GENERALIST

    def list_delegatable(self) -> list[AgentProfile]:
        return [p for p in self._by_id.values() if p.delegatable and not p.supervisor]

    def ensure_default_profile(self) -> dict[str, Any]:
        listed = self.DAC.get_a_b(self.portfolio, self.org, RING, limit=50)
        items = listed.get("items", []) if listed.get("success") else []
        if any(str(i.get("id") or "") == "generalist" for i in items):
            return {
                "success": True,
                "action": "ensure_default_profile",
                "message": "generalist profile already present",
            }
        body = {
            "id": "generalist",
            "code": "D-01",
            "name": "Dumbo Generalist",
            "identity": DEFAULT_GENERALIST.identity,
            "tool_allowlist": ["*"],
            "write_tools": [],
            "delegatable": "false",
            "supervisor": "true",
            "enabled": "true",
            "recursion_limit": "",
            "model": "",
        }
        response, _status = self.DAC.post_a_b(self.portfolio, self.org, RING, body)
        return {
            "success": bool(response.get("success")),
            "action": "ensure_default_profile",
            "output": response,
        }
