from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from flask import current_app

from renglo.auth.auth_controller import AuthController
from renglo.common import load_config
from renglo.data.data_controller import DataController

from .config import ConfigStore
from .demo_tools import DEMO_SCHD_TOOLS
from .profiles import Profiles
from .skills import Skills
from .tools import parse_schd_input_field


def _load_seed_skills() -> List[Dict[str, Any]]:
    seed_path = Path(__file__).resolve().parents[3] / "seed" / "dumbo_skills_examples.json"
    if not seed_path.is_file():
        return []
    with seed_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else []


class DumboOnboardings:
    """Install Dumbo tool, schd entry, singleton config, and default profile."""

    def __init__(self) -> None:
        config = load_config()
        self.DAC = DataController(config=config)
        self.AUC = AuthController(config=config)
        self.bridge: Dict[str, Any] = {}

    def create_tool(self, portfolio: str, tool: str, handle: str) -> Dict[str, Any]:
        action = "create_tool"
        current_app.logger.debug("Installing Dumbo tool in portfolio")

        kwargs = {
            "name": tool,
            "handle": handle,
            "portfolio_id": portfolio,
        }
        response = self.AUC.create_entity("tool", **kwargs)
        self.bridge["tool_id"] = response.get("document", {}).get("_id")

        if not response.get("success"):
            return {
                "success": False,
                "action": action,
                "message": "Could not install tool",
                "input": kwargs,
                "output": response,
            }
        return {
            "success": True,
            "action": action,
            "message": "Tool installed",
            "input": kwargs,
            "output": response,
        }

    def create_schd_tool_doc(self, portfolio: str, org: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        action = "create_schd_tool_doc"
        response, _status = self.DAC.post_a_b(portfolio, org, "schd_tools", doc)
        if not response.get("success"):
            return {
                "success": False,
                "action": action,
                "message": "Could not register schd tool",
                "input": doc,
                "output": response,
            }
        return {
            "success": True,
            "action": action,
            "message": "Scheduler tool registered",
            "input": doc,
            "output": response,
        }

    @staticmethod
    def _schd_input_is_valid_json(raw: Any) -> bool:
        """True when ``input`` is already JSON text (or a structured dict/list)."""
        if isinstance(raw, (dict, list)):
            return True
        if not isinstance(raw, str):
            return False
        s = raw.strip()
        if not s or s == "_":
            return False
        try:
            json.loads(s)
            return True
        except json.JSONDecodeError:
            return False

    def ensure_demo_tools(self, portfolio: str, org: str = "_all") -> Dict[str, Any]:
        """Register demo schd_tools; repair legacy Python-repr ``input`` on existing rows."""
        listed = self.DAC.get_a_b(portfolio, org, "schd_tools", limit=500)
        by_key: Dict[str, Dict[str, Any]] = {}
        if listed.get("success"):
            for doc in listed.get("items", []):
                k = str(doc.get("key") or "").strip()
                if k:
                    by_key[k] = doc

        created: List[str] = []
        repaired: List[str] = []
        skipped: List[str] = []
        failed: List[str] = []
        for seed in DEMO_SCHD_TOOLS:
            key = str(seed.get("key") or "").strip()
            if not key:
                continue
            existing = by_key.get(key)
            if existing is None:
                response = self.create_schd_tool_doc(portfolio, org, seed)
                if response.get("success"):
                    created.append(key)
                    by_key[key] = seed
                else:
                    failed.append(key)
                continue

            # Backward compat: rows written with str(dict) still parse via
            # literal_eval in Tools, but re-write as JSON for consumers/UI.
            if self._schd_input_is_valid_json(existing.get("input")):
                skipped.append(key)
                continue

            # Prefer seed JSON; fall back to re-serializing a legacy parse.
            new_input = seed.get("input")
            if not isinstance(new_input, str) or not new_input.strip():
                parsed = parse_schd_input_field(existing.get("input"))
                if isinstance(parsed, (dict, list)):
                    new_input = json.dumps(parsed, ensure_ascii=False)
                else:
                    failed.append(key)
                    continue

            doc_id = existing.get("_id")
            if not doc_id:
                failed.append(key)
                continue

            patch: Dict[str, Any] = {"input": new_input}
            # Keep instructions in sync when we ship clearer tool guidance.
            if seed.get("instructions"):
                patch["instructions"] = seed["instructions"]

            response, _status = self.DAC.put_a_b_c(
                portfolio, org, "schd_tools", str(doc_id), patch
            )
            if response.get("success"):
                repaired.append(key)
            else:
                failed.append(key)

        return {
            "success": not failed,
            "action": "ensure_demo_tools",
            "created": created,
            "repaired": repaired,
            "skipped": skipped,
            "failed": failed,
        }

    def refresh_s3_cache_for_ring(
        self, portfolio: str, org: str, ring: str
    ) -> Dict[str, Any]:
        action = "refresh_s3_cache"
        try:
            result, _status = self.DAC.refresh_s3_cache(portfolio, org, ring, None)
            return {
                "success": True,
                "action": action,
                "ring": ring,
                "output": result,
            }
        except Exception as exc:
            current_app.logger.warning(
                "S3 cache refresh failed for %s/%s/%s: %s",
                portfolio,
                org,
                ring,
                exc,
            )
            return {
                "success": False,
                "action": action,
                "ring": ring,
                "message": str(exc),
            }

    def refresh_data_caches(self, portfolio: str, org: str = "_all") -> Dict[str, Any]:
        """Rebuild S3 list snapshots once after batch onboarding writes."""
        rings = ("schd_tools", "dumbo_config", "dumbo_profiles", "dumbo_skills")
        results = [self.refresh_s3_cache_for_ring(portfolio, org, ring) for ring in rings]
        failed = [r["ring"] for r in results if not r.get("success")]
        return {
            "success": not failed,
            "action": "refresh_data_caches",
            "results": results,
            "failed": failed,
        }

    def refresh_tree(self) -> Dict[str, Any]:
        action = "refresh_tree"
        response = self.AUC.refresh_tree()
        if not response.get("success"):
            return {
                "success": False,
                "action": action,
                "message": "Tree could not be generated",
                "input": [],
                "output": response,
            }
        return {
            "success": True,
            "action": action,
            "message": "The tree has been generated",
            "input": [],
            "output": response,
        }

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []

        existing_portfolio = None
        if "portfolio" in payload and payload["portfolio"] != "":
            existing_portfolio = str(payload["portfolio"])

        if not existing_portfolio:
            return {"success": False, "output": "No portfolio selected"}

        response_tool = self.create_tool(existing_portfolio, "Dumbo", "dumbo")
        results.append(response_tool)
        if not response_tool["success"]:
            return {"success": False, "output": results}

        agent_tool = {
            "key": "dumbo_agent",
            "name": "Dumbo Agent",
            "goal": "Flat LangGraph smart-model agent harness with HITL approvals",
            "handler": "dumbo/generic_agent",
            "init": "_",
            "instructions": (
                "Routes inbound chat through the Dumbo ReAct LangGraph harness. "
                "Uses dumbo_config for model selection and dumbo_profiles for allowlists."
            ),
            "input": '{"message":"User message text (optional when using chat UI data field)"}',
            "output": "_",
        }
        response_schd = self.create_schd_tool_doc(existing_portfolio, "_all", agent_tool)
        results.append(response_schd)
        if not response_schd["success"]:
            return {"success": False, "output": results}

        cfg = ConfigStore(self.DAC, existing_portfolio, "_all").ensure_defaults()
        results.append(cfg)
        if not cfg.get("success"):
            return {"success": False, "output": results}

        profile = Profiles(self.DAC, existing_portfolio, "_all").ensure_default_profile()
        results.append(profile)
        if not profile.get("success"):
            return {"success": False, "output": results}

        skills = Skills(self.DAC, existing_portfolio, "_all")
        seed_result = skills.ensure_examples(_load_seed_skills())
        results.append(seed_result)
        if not seed_result.get("success"):
            return {"success": False, "output": results}

        demo_tools = self.ensure_demo_tools(existing_portfolio, "_all")
        results.append(demo_tools)
        if not demo_tools.get("success"):
            return {"success": False, "output": results}

        cache_refresh = self.refresh_data_caches(existing_portfolio, "_all")
        results.append(cache_refresh)
        if not cache_refresh.get("success"):
            return {"success": False, "output": results}

        response_tree = self.refresh_tree()
        results.append(response_tree)
        if not response_tree["success"]:
            return {"success": False, "output": results}

        return {
            "success": True,
            "message": "run completed",
            "input": payload,
            "output": results,
        }
