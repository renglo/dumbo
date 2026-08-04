"""Load the singleton ``dumbo_config`` ring document."""

from __future__ import annotations

import logging
from typing import Any, Optional

from .class_prototypes import DumboConfig

_logger = logging.getLogger(__name__)

SINGLETON_ID = "00000000-0000-0000-0000-000000000000"
RING = "dumbo_config"


class ConfigStore:
    """Reads / ensures the extension singleton config."""

    def __init__(self, data_controller: Any, portfolio: str, org: str = "_all") -> None:
        self.DAC = data_controller
        self.portfolio = portfolio
        self.org = org

    def _parse_list(self, raw: Any) -> list[str]:
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        if isinstance(raw, str) and raw.strip() and raw.strip() != "_":
            return [p.strip() for p in raw.split(",") if p.strip()]
        return []

    def load(self) -> DumboConfig:
        try:
            res = self.DAC.get_a_b_c(self.portfolio, self.org, RING, SINGLETON_ID)
            if res.get("success") is False or "_id" not in res:
                listed = self.DAC.get_a_b(self.portfolio, self.org, RING, limit=5)
                items = listed.get("items", []) if listed.get("success") else []
                if not items:
                    _logger.warning("dumbo_config not found; using defaults")
                    return DumboConfig()
                res = next(
                    (i for i in items if str(i.get("_id")) == SINGLETON_ID),
                    items[0],
                )

            model = str(res.get("model") or DumboConfig.model).strip() or DumboConfig.model
            try:
                temperature = float(res.get("temperature", DumboConfig.temperature))
            except (TypeError, ValueError):
                temperature = DumboConfig.temperature
            try:
                recursion_limit = int(res.get("recursion_limit", DumboConfig.recursion_limit))
            except (TypeError, ValueError):
                recursion_limit = DumboConfig.recursion_limit
            try:
                max_history = int(res.get("max_history_messages", DumboConfig.max_history_messages))
            except (TypeError, ValueError):
                max_history = DumboConfig.max_history_messages
            try:
                max_turns = int(res.get("max_history_turns", DumboConfig.max_history_turns))
            except (TypeError, ValueError):
                max_turns = DumboConfig.max_history_turns
            try:
                max_skills = int(res.get("max_loaded_skills", DumboConfig.max_loaded_skills))
            except (TypeError, ValueError):
                max_skills = DumboConfig.max_loaded_skills
            try:
                max_grounding = int(
                    res.get("max_grounding_retries", DumboConfig.max_grounding_retries)
                )
            except (TypeError, ValueError):
                max_grounding = DumboConfig.max_grounding_retries

            grounding_raw = res.get("grounding_enabled", True)
            if isinstance(grounding_raw, str):
                grounding_enabled = grounding_raw.strip().lower() in ("1", "true", "yes", "on")
            else:
                grounding_enabled = bool(grounding_raw)

            return DumboConfig(
                model=model,
                temperature=temperature,
                recursion_limit=recursion_limit,
                default_agent_id=str(
                    res.get("default_agent_id") or DumboConfig.default_agent_id
                ).strip()
                or DumboConfig.default_agent_id,
                max_history_messages=max_history,
                max_history_turns=max_turns,
                max_loaded_skills=max_skills,
                approval_tools=self._parse_list(res.get("approval_tools")),
                grounding_enabled=grounding_enabled,
                max_grounding_retries=max_grounding,
            )
        except Exception as exc:
            _logger.warning("Failed to load dumbo_config: %s", exc)
            return DumboConfig()

    def ensure_defaults(self, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Create the singleton document if missing (used by onboarding)."""
        defaults = {
            "model": "gpt-4.1",
            "temperature": "0",
            "recursion_limit": "40",
            "default_agent_id": "generalist",
            "max_history_messages": "40",
            "max_history_turns": "20",
            "max_loaded_skills": "2",
            "approval_tools": [],
            "grounding_enabled": "true",
            "max_grounding_retries": "1",
        }
        if payload:
            defaults.update(payload)
        existing = self.DAC.get_a_b_c(self.portfolio, self.org, RING, SINGLETON_ID)
        if existing.get("success") is not False and "_id" in existing:
            return {
                "success": True,
                "action": "ensure_dumbo_config",
                "message": "Config already present",
                "output": existing,
            }
        response, _status = self.DAC.post_a_b(self.portfolio, self.org, RING, defaults)
        return {
            "success": bool(response.get("success")),
            "action": "ensure_dumbo_config",
            "message": "Config created" if response.get("success") else "Config create failed",
            "output": response,
        }
