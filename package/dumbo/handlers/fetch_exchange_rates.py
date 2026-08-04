"""Fetch live ECB foreign-exchange rates via Frankfurter (no API key)."""

from __future__ import annotations

import json
import re
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict

from .demo_http import fetch_json, tool_error, tool_ok

_CURRENCY = re.compile(r"^[A-Z]{3}$")


class FetchExchangeRates:
    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = "fetch_exchange_rates"
        base = str(payload.get("from") or payload.get("base") or "USD").strip().upper()
        if not _CURRENCY.match(base):
            return tool_error("from must be a 3-letter ISO currency code (e.g. USD)", action=action, payload=payload)

        to_raw = payload.get("to") or payload.get("targets") or ["EUR", "GBP", "JPY", "MXN"]
        if isinstance(to_raw, str):
            targets = [p.strip().upper() for p in to_raw.split(",") if p.strip()]
        elif isinstance(to_raw, list):
            targets = [str(p).strip().upper() for p in to_raw if str(p).strip()]
        else:
            targets = ["EUR", "GBP", "JPY", "MXN"]

        targets = [c for c in targets if _CURRENCY.match(c) and c != base][:8]
        if not targets:
            return tool_error("to must list at least one 3-letter currency code", action=action, payload=payload)

        symbols = ",".join(targets)
        url = f"https://api.frankfurter.app/latest?from={base}&to={symbols}"

        try:
            doc = fetch_json(url)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            return tool_error(f"Frankfurter API request failed: {exc}", action=action, payload=payload)

        if not isinstance(doc, dict):
            return tool_error("Unexpected Frankfurter API response", action=action, payload=payload)

        return tool_ok(
            action,
            payload,
            {
                "source": "Frankfurter (European Central Bank reference rates)",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "date": doc.get("date"),
                "base": doc.get("base") or base,
                "rates": doc.get("rates") or {},
            },
        )
