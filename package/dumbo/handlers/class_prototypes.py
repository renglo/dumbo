from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional


@dataclass
class SessionEvent:
    """One durable event in the session turn ledger."""

    event_id: str
    session_id: str
    event_type: str
    timestamp: datetime
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolDefinition:
    """Tool the LLM may call (scheduler routing lives in metadata)."""

    tool_name: str
    description: str
    input_schema: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]
    call_id: Optional[str] = None


@dataclass
class ToolResult:
    tool_name: str
    call_id: Optional[str]
    success: bool
    result: Any
    error: Optional[str] = None
    proposed: bool = False
    approval_id: Optional[str] = None


@dataclass
class AgentProfile:
    """Pure-data agent identity + tool allowlist (cos-demo style)."""

    id: str
    code: str
    name: str
    identity: str
    tool_allowlist: list[str] | Literal["all"]
    write_tools: list[str] = field(default_factory=list)
    delegatable: bool = False
    supervisor: bool = False
    enabled: bool = True
    recursion_limit: Optional[int] = None
    model: Optional[str] = None


@dataclass
class DumboConfig:
    """Singleton extension config loaded from ``dumbo_config`` ring."""

    model: str = "gpt-4.1"
    temperature: float = 0.0
    recursion_limit: int = 40
    default_agent_id: str = "generalist"
    max_history_messages: int = 40
    max_history_turns: int = 20
    max_loaded_skills: int = 2
    approval_tools: list[str] = field(default_factory=list)
    grounding_enabled: bool = True
    max_grounding_retries: int = 1
