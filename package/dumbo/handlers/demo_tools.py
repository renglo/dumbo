"""schd_tools documents for Dumbo public-API demo tools.

``schd_tools.input`` is a blueprint string field. Values must be JSON text
(``json.dumps``), not Python dicts — otherwise DataController stores
``str(dict)`` (single quotes) and Dumbo cannot ``json.loads`` the schema.
"""

from __future__ import annotations

import json
from typing import Any


def _input_json(params: dict[str, str]) -> str:
    return json.dumps(params, ensure_ascii=False)


DEMO_SCHD_TOOLS: list[dict[str, Any]] = [
    {
        "key": "fetch_hacker_news",
        "name": "Hacker News top stories",
        "goal": "Live tech news headlines and scores from Hacker News",
        "handler": "dumbo/fetch_hacker_news",
        "init": "_",
        "instructions": (
            "Use for current tech/startup news, trending HN posts, or 'what is hot in tech today'. "
            "Returns real-time data the model cannot know from training."
        ),
        "input": _input_json(
            {
                "limit": "Number of top stories to return (1-20, default 5)",
            }
        ),
        "output": "_",
    },
    {
        "key": "fetch_wikipedia_summary",
        "name": "Wikipedia summary",
        "goal": "Live Wikipedia lead summary for a topic or article title",
        "handler": "dumbo/fetch_wikipedia_summary",
        "init": "_",
        "instructions": (
            "Use when the user asks about a topic, person, place, or concept and you need "
            "an up-to-date encyclopedic summary from Wikipedia."
        ),
        "input": _input_json(
            {
                "title": (
                    "Wikipedia article title or topic "
                    "(e.g. OpenAI, Python programming language)"
                ),
            }
        ),
        "output": "_",
    },
    {
        "key": "fetch_exchange_rates",
        "name": "Live exchange rates",
        "goal": "Current FX rates from ECB via Frankfurter",
        "handler": "dumbo/fetch_exchange_rates",
        "init": "_",
        "instructions": (
            "Use for today's currency conversion rates, forex, or 'how much is X in Y'. "
            "Rates are live market reference data. Always pass from/to currency codes "
            "(e.g. from=SAR, to=USD) matching the user's question."
        ),
        "input": _input_json(
            {
                "from": "Base currency ISO code (default USD)",
                "to": "Comma-separated target codes (default EUR,GBP,JPY,MXN)",
            }
        ),
        "output": "_",
    },
]
