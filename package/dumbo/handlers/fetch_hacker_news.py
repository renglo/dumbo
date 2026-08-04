"""Fetch live top stories from the Hacker News Firebase API (no API key)."""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List

from .demo_http import fetch_json, tool_error, tool_ok


class FetchHackerNews:
    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = "fetch_hacker_news"
        try:
            limit = int(payload.get("limit") or 5)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 20))

        try:
            story_ids = fetch_json("https://hacker-news.firebaseio.com/v0/topstories.json")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            return tool_error(f"HN API request failed: {exc}", action=action, payload=payload)

        if not isinstance(story_ids, list):
            return tool_error("Unexpected HN API response", action=action, payload=payload)

        stories: List[Dict[str, Any]] = []
        for sid in story_ids[:limit]:
            try:
                item = fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
            except Exception:
                continue
            if not isinstance(item, dict):
                continue
            stories.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "url": item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id')}",
                    "score": item.get("score"),
                    "by": item.get("by"),
                    "comments": item.get("descendants"),
                }
            )

        return tool_ok(
            action,
            payload,
            {
                "source": "Hacker News Firebase API",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "count": len(stories),
                "stories": stories,
            },
        )
