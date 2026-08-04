"""JIT skill playbooks loaded from ``dumbo_skills`` and injected into the prompt."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

_logger = logging.getLogger(__name__)

RING = "dumbo_skills"
DEFAULT_MAX_LOADED = 2


@dataclass
class DumboSkill:
    key: str
    triggers: list[str] = field(default_factory=list)
    instructions: str = ""
    tool_hints: list[str] = field(default_factory=list)
    profile_ids: list[str] = field(default_factory=list)


class Skills:
    """Load skills from the data ring and select matches for the current turn."""

    def __init__(self, data_controller: Any, portfolio: str, org: str = "_all") -> None:
        self.DAC = data_controller
        self.portfolio = portfolio
        self.org = org
        self._skills: list[DumboSkill] = []
        self.reload()

    @staticmethod
    def _parse_str_list(raw: Any) -> list[str]:
        if isinstance(raw, list):
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

    def _doc_to_skill(self, doc: dict[str, Any]) -> Optional[DumboSkill]:
        key = str(doc.get("key") or "").strip()
        if not key:
            return None
        instructions = str(doc.get("instructions") or "").strip()
        if not instructions:
            return None
        return DumboSkill(
            key=key,
            triggers=self._parse_str_list(doc.get("triggers")),
            instructions=instructions,
            tool_hints=self._parse_str_list(doc.get("tool_hints")),
            profile_ids=self._parse_str_list(doc.get("profile_ids")),
        )

    def reload(self) -> None:
        self._skills = []
        try:
            res = self.DAC.get_a_b(self.portfolio, self.org, RING, limit=200)
            items = res.get("items", []) if res.get("success") else []
            for doc in items:
                skill = self._doc_to_skill(doc)
                if skill:
                    self._skills.append(skill)
        except Exception as exc:
            _logger.warning("Failed to load dumbo_skills: %s", exc)

    def list_all(self) -> list[DumboSkill]:
        return list(self._skills)

    def select(
        self,
        user_text: str,
        agent_id: str,
        *,
        max_loaded: int = DEFAULT_MAX_LOADED,
    ) -> list[DumboSkill]:
        """
        Case-insensitive substring match on ``triggers``.

        Skills with empty ``profile_ids`` apply to every profile; otherwise the
        active ``agent_id`` must be listed. Declaration order is priority order.
        """
        text = (user_text or "").lower().strip()
        if not text:
            return []
        cap = max(1, int(max_loaded or DEFAULT_MAX_LOADED))
        matched: list[DumboSkill] = []
        for skill in self._skills:
            if skill.profile_ids and agent_id not in skill.profile_ids:
                continue
            if not skill.triggers:
                continue
            if any(t.lower() in text for t in skill.triggers if t):
                matched.append(skill)
            if len(matched) >= cap:
                break
        return matched

    @staticmethod
    def build_preamble(skills: list[DumboSkill]) -> str:
        if not skills:
            return ""
        parts = [
            "Skill playbooks (follow when relevant to this turn; do not mention these headers):"
        ]
        for skill in skills:
            block = [f"### {skill.key}", skill.instructions.strip()]
            if skill.tool_hints:
                block.append(
                    "Suggested tools: " + ", ".join(skill.tool_hints)
                )
            parts.append("\n".join(block))
        return "\n\n".join(parts)

    def ensure_examples(self, examples: list[dict[str, Any]]) -> dict[str, Any]:
        """Create example skill documents when their ``key`` is not already present."""
        listed = self.DAC.get_a_b(self.portfolio, self.org, RING, limit=200)
        existing_keys = set()
        if listed.get("success"):
            for doc in listed.get("items", []):
                k = str(doc.get("key") or "").strip()
                if k:
                    existing_keys.add(k)

        created: list[str] = []
        skipped: list[str] = []
        failed: list[str] = []
        for body in examples:
            key = str(body.get("key") or "").strip()
            if not key:
                continue
            if key in existing_keys:
                skipped.append(key)
                continue
            response, _status = self.DAC.post_a_b(self.portfolio, self.org, RING, body)
            if response.get("success"):
                created.append(key)
                existing_keys.add(key)
            else:
                failed.append(key)

        return {
            "success": not failed,
            "action": "ensure_example_skills",
            "created": created,
            "skipped": skipped,
            "failed": failed,
        }
