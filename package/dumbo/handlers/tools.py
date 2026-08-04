"""
Build ToolDefinition rows from ``schd_tools`` (same contract as CLAW Tools).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .class_prototypes import ToolDefinition

_logger = logging.getLogger(__name__)


class Tools:
    """Tool registry backed by ``schd_tools`` for the active org, filtered by profile allowlist."""

    @staticmethod
    def normalize_openai_function_parameters(raw: Any) -> tuple[dict[str, Any], bool]:
        if not isinstance(raw, dict):
            return {"type": "object", "properties": {}}, True

        t = raw.get("type")
        corrupt_type = t is None or (
            isinstance(t, str) and t.strip().lower() in ("none", "null", "")
        )
        props = raw.get("properties")
        props_ok = isinstance(props, dict)

        if corrupt_type:
            if props_ok:
                out = dict(raw)
                out["type"] = "object"
                if not isinstance(out.get("properties"), dict):
                    out["properties"] = {}
                return out, True
            return {"type": "object", "properties": {}}, True

        if isinstance(t, str) and t.lower() == "object":
            out = dict(raw)
            out["type"] = "object"
            fixed = not isinstance(raw.get("properties"), dict)
            if not isinstance(out.get("properties"), dict):
                out["properties"] = {}
            return out, fixed

        if props_ok:
            merged: dict[str, Any] = {
                "type": "object",
                "properties": dict(props),
            }
            if isinstance(raw.get("required"), list):
                merged["required"] = raw["required"]
            if "additionalProperties" in raw:
                merged["additionalProperties"] = raw["additionalProperties"]
            return merged, True

        return {"type": "object", "properties": {}}, True

    @staticmethod
    def schd_input_to_json_schema(raw: Any) -> dict[str, Any]:
        if isinstance(raw, list):
            properties: dict[str, Any] = {}
            required: list[str] = []
            for param in raw:
                if not isinstance(param, dict):
                    continue
                name = str(param.get("name") or "").strip()
                if not name:
                    continue
                hint = str(param.get("hint") or param.get("description", "") or "")
                ptype = str(param.get("type", "string")).lower()
                if ptype not in ("string", "number", "integer", "boolean", "array", "object"):
                    ptype = "string"
                properties[name] = {"type": ptype, "description": hint}
                if param.get("required", False):
                    required.append(name)
            out: dict[str, Any] = {"type": "object", "properties": properties}
            if required:
                out["required"] = required
            return out

        if isinstance(raw, dict):
            if raw.get("properties") is not None or str(raw.get("type") or "").lower() == "object":
                return dict(raw)
            properties = {}
            required = []
            for key, val in raw.items():
                if key in ("type", "properties", "required", "additionalProperties"):
                    continue
                desc = val if isinstance(val, str) else str(val)
                properties[str(key)] = {"type": "string", "description": desc}
                required.append(str(key))
            if properties:
                return {"type": "object", "properties": properties, "required": required}

        return {"type": "object", "properties": {}}

    @staticmethod
    def extension_handler_from_doc(doc: dict[str, Any]) -> tuple[str, str]:
        raw = str(doc.get("handler") or "").strip()
        parts = [p for p in raw.split("/") if p]
        if not parts:
            return str(doc.get("extension") or "").strip(), ""
        extension = parts[0]
        if len(parts) == 2:
            handler = parts[1]
        elif len(parts) >= 3:
            handler = parts[1] + parts[2]
        else:
            handler = str(doc.get("handler") or "").strip()
        return extension, handler

    @staticmethod
    def tool_definition_from_doc(doc: dict[str, Any]) -> Optional[ToolDefinition]:
        tool_key = str(doc.get("key") or "").strip()
        if not tool_key:
            return None

        label = doc.get("name")
        label_str = str(label).strip() if label is not None else ""
        goal = str(doc.get("goal", "") or "").strip()
        instr = str(doc.get("instructions", "") or "").strip()
        if label_str:
            desc = f"{label_str}. {goal} {instr}".strip()
        else:
            desc = f"{goal} {instr}".strip()

        schema: Any = doc.get("input")
        if isinstance(schema, str):
            s = schema.strip()
            if not s:
                schema = {}
            else:
                try:
                    schema = json.loads(s)
                except Exception:
                    _logger.warning(
                        "dumbo.tools: invalid JSON in input for tool %r; using empty object schema",
                        tool_key,
                    )
                    schema = {}
        schema = Tools.schd_input_to_json_schema(schema)
        schema, repaired = Tools.normalize_openai_function_parameters(schema)
        if repaired:
            _logger.warning(
                "dumbo.tools: repaired input schema for tool %r",
                tool_key,
            )

        tool_init = doc.get("tool_init")
        if tool_init is None:
            tool_init = doc.get("init")
        if isinstance(tool_init, str):
            try:
                tool_init = json.loads(tool_init) if tool_init.strip() not in ("", "_") else {}
            except Exception:
                tool_init = {}
        if not isinstance(tool_init, dict):
            tool_init = {}

        extension, handler = Tools.extension_handler_from_doc(doc)
        requires_approval = bool(tool_init.get("requires_approval", False))

        meta: dict[str, Any] = {
            "_id": doc.get("_id"),
            "source": "schd_tools",
            "extension": extension,
            "handler": handler,
            "tool_init": tool_init,
            "requires_approval": requires_approval,
        }
        if label_str:
            meta["label"] = label_str

        return ToolDefinition(
            tool_name=tool_key,
            description=desc,
            input_schema=schema,
            metadata=meta,
        )

    @staticmethod
    def _shortlist_includes_all(shortlist: Optional[list[str]]) -> bool:
        if not shortlist:
            return True
        return any(str(x).strip() == "*" for x in shortlist)

    @staticmethod
    def tool_definitions_from_items(
        items: list[dict[str, Any]],
        shortlist: Optional[list[str]] = None,
    ) -> list[ToolDefinition]:
        filter_by_key = shortlist is not None and not Tools._shortlist_includes_all(shortlist)
        out: list[ToolDefinition] = []
        for doc in items:
            key = str(doc.get("key") or "").strip()
            if filter_by_key and key not in (shortlist or []):
                continue
            # Never expose the dumbo agent itself as a callable tool.
            if key in ("dumbo_agent", "generic_agent"):
                continue
            td = Tools.tool_definition_from_doc(doc)
            if td is not None:
                out.append(td)
        return out

    @staticmethod
    def tool_definitions_to_openai(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        api_tools: list[dict[str, Any]] = []
        for td in tools:
            params = td.input_schema if isinstance(td.input_schema, dict) else {}
            if not params:
                params = {"type": "object", "properties": {}}
            api_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": td.tool_name,
                        "description": (td.description or "")[:8000],
                        "parameters": params,
                    },
                }
            )
        return api_tools

    def __init__(
        self,
        data_controller: Any,
        portfolio: str,
        org: str,
        shortlist: Optional[list[str]] = None,
    ) -> None:
        self.DAC = data_controller
        self.portfolio = portfolio
        self.org = org
        res = self.DAC.get_a_b(self.portfolio, self.org, "schd_tools", limit=500)
        self.raw_list_tools: list[dict[str, Any]] = (
            res.get("items", []) if res.get("success") else []
        )
        sl = shortlist if shortlist else None
        self.definitions: list[ToolDefinition] = Tools.tool_definitions_from_items(
            self.raw_list_tools, shortlist=sl
        )
        if not self.definitions and self.raw_list_tools and sl:
            _logger.warning(
                "dumbo.tools: %d schd_tools in org=%r but none matched allowlist %r",
                len(self.raw_list_tools),
                org,
                sl,
            )
        elif not self.raw_list_tools:
            _logger.warning(
                "dumbo.tools: no schd_tools documents for portfolio=%r org=%r",
                portfolio,
                org,
            )

    def list_tools(self) -> list[ToolDefinition]:
        return self.definitions

    def by_name(self) -> dict[str, ToolDefinition]:
        return {td.tool_name: td for td in self.definitions}
