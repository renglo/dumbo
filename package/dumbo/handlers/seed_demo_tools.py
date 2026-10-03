"""Re-register Dumbo public-API demo schd_tools (idempotent; safe on existing portfolios)."""

from __future__ import annotations

from typing import Any, Dict

from ..lib.describe import describe_document

from .dumbo_onboardings import DumboOnboardings


class SeedDemoTools:
    def __init__(self) -> None:
        self._onboarding = DumboOnboardings()

    def describe(self, payload=None):
        return describe_document(
            "seed_demo_tools",
            "Seed demo tools",
            "Re-register Dumbo public-API demo tools for one org. portfolio is injected by the platform.",
            {
                "org": {
                    "type": "string",
                    "title": "Org",
                    "description": "Org to seed. Defaults to _all.",
                    "default": "_all",
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "tools": {"type": "object"},
                    "cache": {"type": "object"},
                    "tree": {"type": "object"},
                },
            },
        )

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        portfolio = str(payload.get("portfolio") or "").strip()
        if not portfolio:
            return {"success": False, "output": "portfolio is required"}

        org = str(payload.get("org") or "_all").strip() or "_all"
        result = self._onboarding.ensure_demo_tools(portfolio, org)
        if not result.get("success"):
            return {"success": False, "output": result}

        cache = self._onboarding.refresh_s3_cache_for_ring(portfolio, org, "schd_tools")
        if not cache.get("success"):
            return {"success": False, "output": {"tools": result, "cache": cache}}

        tree = self._onboarding.refresh_tree()
        return {
            "success": True,
            "action": "seed_demo_tools",
            "input": payload,
            "output": {"tools": result, "cache": cache, "tree": tree},
        }
