"""
Dumbo flat LangGraph agent harness.

Topology: load_context → persist → call_llm ⇄ execute_tool → grounding_gate → END

Persistence uses Renglo session turns (no Postgres checkpointer). HITL write tools
propose into ``dumbo_approvals``; OK/NO shortcuts are handled before the graph runs.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from renglo.agent.websocket_client import WebSocketClient
from renglo.common import load_config
from renglo.data.data_controller import DataController
from renglo.schd.schd_controller import SchdController
from renglo.session.session_controller import SessionController

from .approvals import Approvals
from .class_prototypes import AgentProfile, SessionEvent, ToolDefinition, ToolResult
from .config import ConfigStore
from .delegation import run_subagent_loop
from .models import Models
from .profiles import Profiles
from .sessions import Sessions
from .skills import Skills
from .tools import Tools

_logger = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    session_id: str
    agent_id: str
    inbound_message: str
    messages: List[Dict[str, Any]]
    reply: str
    grounding_retries: int
    turn_count: int
    pending_approvals: List[Dict[str, Any]]
    loaded_skill_keys: List[str]
    metadata: Dict[str, Any]


@dataclass
class RequestContext:
    connection_id: str = ""
    portfolio: str = ""
    org: str = ""
    public_user: str = ""
    entity_type: str = ""
    entity_id: str = ""
    thread: str = ""
    message: str = ""
    agent_id: str = ""
    request_id: str = ""


request_context: ContextVar[RequestContext] = ContextVar(
    "dumbo_request_context",
    default=RequestContext(),
)


DELEGATE_TOOL = ToolDefinition(
    tool_name="delegate_to_agent",
    description=(
        "Delegate a focused task to a specialist agent profile. "
        "Use when a specialist is better suited. Depth-1 only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "Target profile id (must be delegatable).",
            },
            "task": {
                "type": "string",
                "description": "Clear task description for the sub-agent.",
            },
        },
        "required": ["agent_id", "task"],
    },
    metadata={"source": "dumbo_harness", "requires_approval": False},
)


class GenericAgent:
    """Scheduler-facing Dumbo entry point."""

    def __init__(self) -> None:
        self.config = load_config()
        self.SSC = SessionController(config=self.config)
        self.DAC = DataController(config=self.config)
        self.SHC = SchdController(config=self.config)
        ws_url = str(self.config.get("WEBSOCKET_CONNECTIONS", "") or "")
        self._ws = WebSocketClient(ws_url)
        self._sessions: Optional[Sessions] = None
        self._models: Optional[Models] = None
        self._profile: Optional[AgentProfile] = None
        self._tool_defs: list[ToolDefinition] = []
        self._approvals: Optional[Approvals] = None
        self._ext_config = None
        self._profiles: Optional[Profiles] = None
        self._skills: Optional[Skills] = None
        self._last_assistant_event_id: Optional[str] = None
        self.graph = self._build_graph()

    def _get_context(self) -> RequestContext:
        return request_context.get()

    def _set_context(self, context: RequestContext) -> None:
        request_context.set(context)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _send_ws(self, doc: Dict[str, Any], connection_id: Optional[str] = None) -> bool:
        cid = connection_id or self._get_context().connection_id
        if not cid or not self._ws.is_configured():
            return False
        return self._ws.send_message(cid, doc)

    def on_stream(self, message: Dict[str, Any]) -> None:
        body = {"channel": "dumbo_stream", **message}
        doc = {
            "_type": "dumbo_stream",
            "_out": {"role": "assistant", "content": json.dumps(body, default=str)},
        }
        self._send_ws(doc)

    def _emit_roll(self, event: SessionEvent) -> None:
        if event.event_type in ("user_message", "assistant_message"):
            text = str(event.payload.get("text") or "")
            role = "user" if event.event_type == "user_message" else "assistant"
            self._send_ws(
                {
                    "_type": event.event_type,
                    "_out": {"role": role, "content": text},
                    "_meta": {
                        "event_id": event.event_id,
                        "session_id": event.session_id,
                        "timestamp": event.timestamp.isoformat(),
                    },
                }
            )
        else:
            self._send_ws(
                {
                    "_type": event.event_type,
                    "_out": {
                        "role": "system",
                        "content": event.payload,
                    },
                    "_meta": {
                        "event_id": event.event_id,
                        "session_id": event.session_id,
                        "timestamp": event.timestamp.isoformat(),
                    },
                }
            )

    def _save_event(self, event: SessionEvent) -> None:
        if not self._sessions:
            return
        try:
            self._sessions.append_event(event)
            if event.event_type == "assistant_message":
                self._last_assistant_event_id = event.event_id
        except Exception as exc:
            _logger.warning("Failed to persist event %s: %s", event.event_type, exc)
            return
        self._emit_roll(event)

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = "run > dumbo/generic_agent"
        context = RequestContext(request_id=str(uuid.uuid4()))

        if isinstance(payload, str):
            try:
                payload = json.loads(payload) if payload.strip() else {}
            except json.JSONDecodeError:
                payload = {}
        payload = payload if isinstance(payload, dict) else {}

        if "connectionId" in payload:
            context.connection_id = payload["connectionId"]
        if "portfolio" in payload:
            context.portfolio = payload["portfolio"]
        else:
            return {
                "success": False,
                "action": action,
                "input": payload,
                "output": "No portfolio provided",
            }
        context.org = payload.get("org") or "_all"
        context.public_user = str(payload.get("public_user") or "")
        context.entity_type = payload.get("entity_type") or "dumbo-chat"
        context.entity_id = payload.get("entity_id") or f"dumbo-{context.org}"
        context.thread = payload.get("thread") or "main"
        data = payload.get("data")
        if isinstance(data, dict):
            context.message = str(data.get("message") or data.get("text") or "")
        else:
            context.message = str(data or payload.get("message") or "")
        context.agent_id = str(
            payload.get("agent_id") or payload.get("agentId") or ""
        ).strip()
        self._set_context(context)

        # Load extension data and profile for the active org (chat URL org).
        cfg_store = ConfigStore(self.DAC, context.portfolio, context.org)
        ext_cfg = cfg_store.load()
        self._ext_config = ext_cfg
        profiles = Profiles(self.DAC, context.portfolio, context.org)
        self._profiles = profiles
        profile = profiles.get(context.agent_id or None, ext_cfg.default_agent_id)
        self._profile = profile

        skills = Skills(self.DAC, context.portfolio, context.org)
        self._skills = skills

        model_name = profile.model or ext_cfg.model
        self._models = Models(
            config=self.config,
            model=model_name,
            temperature=ext_cfg.temperature,
        )

        self._approvals = Approvals(
            self.DAC,
            context.portfolio,
            context.org,
            entity_type=context.entity_type,
            entity_id=context.entity_id,
            thread=context.thread,
        )

        # HITL: bare OK/YES/NO apply only when a proposal is pending for this chat;
        # explicit ids (OK <uuid>, approve:<uuid>) always route to approval handling.
        shortcut = Approvals.parse_shortcut(context.message)
        if shortcut:
            has_explicit_id = bool(shortcut.get("approval_id"))
            has_pending = bool(self._approvals.list_pending(limit=1))
            if has_explicit_id or has_pending:
                return self._handle_approval_shortcut(action, payload, context, shortcut)

        # Bind tools: org schd_tools ∩ profile.tool_allowlist (dumbo_profiles).
        allowlist = profile.tool_allowlist
        payload_shortlist = payload.get("tool_allowlist") or payload.get("tool_shortlist")
        if payload_shortlist:
            allowlist = profiles._parse_allowlist(payload_shortlist)
        shortlist = Profiles.allowlist_to_shortlist(allowlist)
        tools = Tools(self.DAC, context.portfolio, context.org, shortlist=shortlist)
        self._tool_defs = list(tools.list_tools())
        if not self._tool_defs:
            _logger.warning(
                "Dumbo: no tools bound for portfolio=%s org=%s profile=%s allowlist=%s",
                context.portfolio,
                context.org,
                profile.id,
                shortlist or "*",
            )
        else:
            _logger.info(
                "Dumbo: bound %d tools: %s",
                len(self._tool_defs),
                ", ".join(td.tool_name for td in self._tool_defs[:20]),
            )
        if profile.supervisor:
            # Bind delegate tool if any specialists exist
            if profiles.list_delegatable():
                self._tool_defs.append(DELEGATE_TOOL)

        ss = Sessions(
            session_controller=self.SSC,
            portfolio=context.portfolio,
            org=context.org,
            entity_type=context.entity_type,
            entity_id=context.entity_id,
            thread_id=context.thread,
        )
        self._sessions = ss

        try:
            ss.create_turn(
                {
                    "portfolio": context.portfolio,
                    "org": context.org,
                    "public_user": context.public_user or False,
                    "entity_type": context.entity_type,
                    "entity_id": context.entity_id,
                    "thread": context.thread,
                    "agent_id": profile.id,
                    "request_id": context.request_id,
                }
            )

            history = self._load_history(
                ss,
                max_messages=ext_cfg.max_history_messages,
                max_turns=ext_cfg.max_history_turns,
            )
            pending = self._approvals.list_pending(limit=10)
            matched_skills = self._skills.select(
                context.message,
                profile.id,
                max_loaded=ext_cfg.max_loaded_skills,
            )

            initial_state: AgentState = {
                "session_id": ss.session_id,
                "agent_id": profile.id,
                "inbound_message": context.message,
                "messages": history,
                "reply": "",
                "grounding_retries": 0,
                "turn_count": 0,
                "pending_approvals": pending,
                "loaded_skill_keys": [s.key for s in matched_skills],
                "metadata": payload.get("metadata") or {},
            }

            recursion = profile.recursion_limit or ext_cfg.recursion_limit
            try:
                final_state = self.graph.invoke(
                    initial_state,
                    {"recursion_limit": max(10, int(recursion))},
                )
            except Exception as exc:
                _logger.exception("Dumbo graph failed: %s", exc)
                # Best-effort partial reply
                partial = (
                    "I hit an internal limit or error while working on that. "
                    f"Details: {exc}"
                )
                self._save_event(
                    SessionEvent(
                        event_id=str(uuid.uuid4()),
                        session_id=ss.session_id,
                        event_type="assistant_message",
                        timestamp=self._now(),
                        payload={"text": partial},
                    )
                )
                return {
                    "success": False,
                    "action": action,
                    "input": payload,
                    "output": {
                        "error": str(exc),
                        "reply": partial,
                        "session_id": ss.session_id,
                        "turn_id": ss.get_active_turn_id(),
                        "assistant_event_id": self._last_assistant_event_id,
                        "entity_type": context.entity_type,
                        "entity_id": context.entity_id,
                        "thread": context.thread,
                    },
                }

            summary = {
                "session_id": ss.session_id,
                "turn_id": ss.get_active_turn_id(),
                "assistant_event_id": self._last_assistant_event_id,
                "entity_type": context.entity_type,
                "entity_id": context.entity_id,
                "thread": context.thread,
                "agent_id": profile.id,
                "model": model_name,
                "reply": final_state.get("reply"),
                "loaded_skill_keys": final_state.get("loaded_skill_keys") or [],
                "pending_approvals": [
                    {
                        "_id": p.get("_id"),
                        "tool_key": p.get("tool_key"),
                        "status": p.get("status"),
                    }
                    for p in (self._approvals.list_pending(limit=10) if self._approvals else [])
                ],
            }
            return {
                "success": True,
                "action": action,
                "input": payload,
                "output": summary,
            }
        finally:
            self._sessions = None
            self._models = None
            self._approvals = None
            self._last_assistant_event_id = None

    def _handle_approval_shortcut(
        self,
        action: str,
        payload: Dict[str, Any],
        context: RequestContext,
        shortcut: Dict[str, Any],
    ) -> Dict[str, Any]:
        assert self._approvals is not None
        ss = Sessions(
            session_controller=self.SSC,
            portfolio=context.portfolio,
            org=context.org,
            entity_type=context.entity_type,
            entity_id=context.entity_id,
            thread_id=context.thread,
        )
        self._sessions = ss
        try:
            ss.create_turn(
                {
                    "portfolio": context.portfolio,
                    "org": context.org,
                    "public_user": context.public_user or False,
                    "entity_type": context.entity_type,
                    "entity_id": context.entity_id,
                    "thread": context.thread,
                    "request_id": context.request_id,
                }
            )
            self._save_event(
                SessionEvent(
                    event_id=str(uuid.uuid4()),
                    session_id=ss.session_id,
                    event_type="user_message",
                    timestamp=self._now(),
                    payload={"text": context.message},
                )
            )

            approval_id = shortcut.get("approval_id")
            if not approval_id:
                pending = self._approvals.list_pending(limit=1)
                if not pending:
                    reply = "There is no pending approval to act on."
                    self._save_event(
                        SessionEvent(
                            event_id=str(uuid.uuid4()),
                            session_id=ss.session_id,
                            event_type="assistant_message",
                            timestamp=self._now(),
                            payload={"text": reply},
                        )
                    )
                    return {
                        "success": True,
                        "action": action,
                        "input": payload,
                        "output": {"reply": reply, "hitl": True},
                    }
                approval_id = str(pending[0].get("_id"))

            decision = "approved" if shortcut.get("decision") == "approved" else "rejected"
            result = self._approvals.resolve_and_execute(
                approval_id,
                decision=decision,
                schd_controller=self.SHC,
                resolved_by=context.public_user or "user",
            )
            if decision == "rejected":
                reply = f"Rejected approval `{approval_id}` for tool `{result.get('tool_key')}`."
            elif result.get("success"):
                reply = (
                    f"Approved and executed `{result.get('tool_key')}` "
                    f"(approval `{approval_id}`).\n\n"
                    f"Result:\n{json.dumps(result.get('output'), default=str, indent=2)[:4000]}"
                )
            else:
                reply = (
                    f"Approval `{approval_id}` failed: {result.get('error') or result.get('output')}"
                )

            self._save_event(
                SessionEvent(
                    event_id=str(uuid.uuid4()),
                    session_id=ss.session_id,
                    event_type="dumbo_approval",
                    timestamp=self._now(),
                    payload=result,
                )
            )
            self._save_event(
                SessionEvent(
                    event_id=str(uuid.uuid4()),
                    session_id=ss.session_id,
                    event_type="assistant_message",
                    timestamp=self._now(),
                    payload={"text": reply},
                )
            )
            return {
                "success": bool(result.get("success")) or decision == "rejected",
                "action": action,
                "input": payload,
                "output": {"reply": reply, "hitl": True, "result": result},
            }
        finally:
            self._sessions = None

    def _load_history(
        self,
        ss: Sessions,
        *,
        max_messages: int,
        max_turns: int,
    ) -> List[Dict[str, Any]]:
        """Cross-turn continuity via windowed session scan (newest turns first)."""
        messages: List[Dict[str, Any]] = []
        for event in ss.get_recent_chat_events(
            ss.session_id,
            max_messages=max_messages,
            max_turns=max_turns,
        ):
            if event.event_type == "channel_delivery":
                status = str(event.payload.get("status") or "")
                if status != "failed":
                    continue
                channel = str(event.payload.get("channel") or "channel")
                err = (
                    event.payload.get("provider_error")
                    or event.payload.get("error")
                    or event.payload.get("provider_status")
                    or "unknown error"
                )
                if isinstance(err, (dict, list)):
                    err = json.dumps(err, default=str)[:400]
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            f"[channel_delivery failed on {channel}] "
                            f"The previous assistant reply was not delivered: {err}"
                        ),
                    }
                )
                continue
            role = "user" if event.event_type == "user_message" else "assistant"
            text = event.payload.get("text") or event.payload.get("message") or ""
            if str(text).strip():
                messages.append({"role": role, "content": str(text)})
        return messages

    def _user_text_for_skills(self, state: AgentState) -> str:
        text = (state.get("inbound_message") or "").strip()
        if text:
            return text
        for m in reversed(state.get("messages") or []):
            if m.get("role") == "user":
                return str(m.get("content") or "").strip()
        return ""

    # ------------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------------

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("load_context", self._load_context)
        builder.add_node("persist", self._persist)
        builder.add_node("call_llm", self._call_llm)
        builder.add_node("execute_tool", self._execute_tool)
        builder.add_node("grounding_gate", self._grounding_gate)

        builder.add_edge(START, "load_context")
        builder.add_edge("load_context", "persist")
        builder.add_edge("persist", "call_llm")
        builder.add_conditional_edges(
            "call_llm",
            self._route_after_llm,
            {"execute_tool": "execute_tool", "grounding_gate": "grounding_gate"},
        )
        builder.add_edge("execute_tool", "call_llm")
        builder.add_conditional_edges(
            "grounding_gate",
            self._route_after_gate,
            {"call_llm": "call_llm", "end": END},
        )
        return builder.compile()

    def _route_after_llm(self, state: AgentState) -> str:
        messages = state.get("messages") or []
        if not messages:
            return "grounding_gate"
        last = messages[-1]
        if last.get("role") == "assistant" and last.get("tool_calls"):
            return "execute_tool"
        return "grounding_gate"

    def _route_after_gate(self, state: AgentState) -> str:
        messages = state.get("messages") or []
        if messages and messages[-1].get("role") == "user" and messages[-1].get(
            "_grounding_correction"
        ):
            return "call_llm"
        return "end"

    def _load_context(self, state: AgentState) -> AgentState:
        # Context already seeded from session history; attach pending-approval preamble later in call_llm.
        return {
            "turn_count": int(state.get("turn_count") or 0),
            "grounding_retries": int(state.get("grounding_retries") or 0),
        }

    def _persist(self, state: AgentState) -> AgentState:
        """Early-persist user message (before tools) for approval timestamping."""
        text = state.get("inbound_message") or ""
        messages = list(state.get("messages") or [])
        if text:
            messages.append({"role": "user", "content": text})
            self._save_event(
                SessionEvent(
                    event_id=str(uuid.uuid4()),
                    session_id=state["session_id"],
                    event_type="user_message",
                    timestamp=self._now(),
                    payload={"text": text},
                )
            )
        return {"messages": messages}

    def _build_system_messages(self, state: AgentState) -> List[Dict[str, Any]]:
        assert self._profile is not None
        assert self._ext_config is not None
        ctx = self._get_context()
        layers: List[Dict[str, Any]] = [
            {"role": "system", "content": self._profile.identity},
        ]

        if self._skills:
            matched = self._skills.select(
                self._user_text_for_skills(state),
                self._profile.id,
                max_loaded=self._ext_config.max_loaded_skills,
            )
            preamble = Skills.build_preamble(matched)
            if preamble:
                layers.append({"role": "system", "content": preamble})

        dynamic_parts = [
            f"Current UTC time: {datetime.now(timezone.utc).isoformat()}",
            f"Portfolio: {ctx.portfolio} | Org: {ctx.org}",
            f"Agent profile: {self._profile.id} ({self._profile.name})",
            f"Model: {self._models.model if self._models else self._ext_config.model}",
        ]
        pending = state.get("pending_approvals") or []
        if pending:
            lines = ["Pending approvals (user may reply OK / NO):"]
            for p in pending[:5]:
                lines.append(
                    f"- id={p.get('_id')} tool={p.get('tool_key')} "
                    f"args={json.dumps(p.get('arguments') or {}, default=str)[:200]}"
                )
            dynamic_parts.append("\n".join(lines))
        if self._profile.supervisor and self._profiles:
            specs = self._profiles.list_delegatable()
            if specs:
                dynamic_parts.append(
                    "Delegatable agents: "
                    + ", ".join(f"{s.id} ({s.name})" for s in specs)
                )
        if self._tool_defs:
            names = ", ".join(td.tool_name for td in self._tool_defs)
            dynamic_parts.append(
                f"Bound tools for profile {self._profile.id} (allowlist applied): {names}"
            )
            dynamic_parts.append(
                "When the user asks for live, current, or real-time information "
                "(news, exchange rates, encyclopedic facts), call the matching tool "
                "in the same turn. Do not say you are fetching or ask them to wait "
                "without issuing a tool call. Do not invent live data."
            )
        layers.append({"role": "system", "content": "\n".join(dynamic_parts)})
        return layers

    def _call_llm(self, state: AgentState) -> AgentState:
        assert self._models is not None
        assert self._profile is not None

        oa_tools = Tools.tool_definitions_to_openai(self._tool_defs)
        history = list(state.get("messages") or [])
        llm_messages = self._build_system_messages(state) + self._sanitize_messages_for_llm(
            history
        )

        resp = self._models.complete(
            llm_messages,
            tools=oa_tools if oa_tools else None,
            tool_choice="auto",
            model=self._profile.model or self._models.model,
        )

        msg = (resp.get("choices") or [{}])[0].get("message") or {}
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        assistant_row: Dict[str, Any] = {"role": "assistant", "content": content or ""}
        if tool_calls:
            assistant_row["tool_calls"] = tool_calls
            history.append(assistant_row)
            return {
                "messages": history,
                "reply": "",
                "turn_count": int(state.get("turn_count") or 0) + 1,
            }

        history.append(assistant_row)
        if content:
            self._save_event(
                SessionEvent(
                    event_id=str(uuid.uuid4()),
                    session_id=state["session_id"],
                    event_type="assistant_message",
                    timestamp=self._now(),
                    payload={"text": content},
                )
            )
        return {
            "messages": history,
            "reply": content,
            "turn_count": int(state.get("turn_count") or 0) + 1,
        }

    def _sanitize_messages_for_llm(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure tool message pairing is valid for the API."""
        out: List[Dict[str, Any]] = []
        pending_tool_ids: set[str] = set()
        for m in messages:
            role = m.get("role")
            if role == "assistant" and m.get("tool_calls"):
                out.append(m)
                for tc in m.get("tool_calls") or []:
                    pending_tool_ids.add(str(tc.get("id") or ""))
                continue
            if role == "tool":
                tid = str(m.get("tool_call_id") or "")
                if tid and tid in pending_tool_ids:
                    out.append(m)
                    pending_tool_ids.discard(tid)
                continue
            if role in ("user", "assistant", "system"):
                # Drop bare assistant tool_calls leftovers
                if role == "assistant" and m.get("tool_calls") and not m.get("content"):
                    continue
                row = {"role": role, "content": m.get("content") or ""}
                out.append(row)
        return out

    def _requires_approval(self, td: ToolDefinition) -> bool:
        assert self._profile is not None
        assert self._ext_config is not None
        if td.tool_name == "delegate_to_agent":
            return False
        meta = td.metadata or {}
        if meta.get("requires_approval"):
            return True
        if td.tool_name in (self._profile.write_tools or []):
            return True
        if td.tool_name in (self._ext_config.approval_tools or []):
            return True
        return False

    def _execute_one_tool(
        self,
        name: str,
        args: dict[str, Any],
        call_id: Optional[str],
        session_id: str,
    ) -> ToolResult:
        assert self._approvals is not None
        ctx = self._get_context()

        if name == "delegate_to_agent":
            return self._run_delegation(args, call_id, session_id)

        by_name = {td.tool_name: td for td in self._tool_defs}
        td = by_name.get(name)
        if not td:
            return ToolResult(
                tool_name=name,
                call_id=call_id,
                success=False,
                result={},
                error=f"Unknown tool '{name}'",
            )

        if self._requires_approval(td):
            meta = td.metadata or {}
            proposed = self._approvals.propose(
                tool_key=name,
                arguments=args,
                call_id=call_id,
                request_id=ctx.request_id,
                extension=str(meta.get("extension") or ""),
                handler=str(meta.get("handler") or ""),
                tool_init=meta.get("tool_init") if isinstance(meta.get("tool_init"), dict) else {},
                rationale=str(args.get("rationale") or ""),
            )
            return ToolResult(
                tool_name=name,
                call_id=call_id,
                success=True,
                result={
                    "status": "proposed_pending_approval",
                    "approval_id": proposed["approval_id"],
                    "tool_key": name,
                    "arguments": args,
                    "guidance": (
                        "Tell the user what you proposed and ask them to reply "
                        "OK to approve or NO to reject "
                        f"(or OK {proposed['approval_id']})."
                    ),
                },
                proposed=True,
                approval_id=proposed["approval_id"],
            )

        meta = td.metadata or {}
        extension = str(meta.get("extension") or "").strip()
        handler = str(meta.get("handler") or "").strip()
        if not extension or not handler:
            return ToolResult(
                tool_name=name,
                call_id=call_id,
                success=False,
                result={},
                error="Tool missing extension/handler metadata",
            )

        params = dict(args)
        init = meta.get("tool_init")
        params["_init"] = init if isinstance(init, dict) else {}
        params["_delegated"] = True
        if ctx.connection_id:
            params.setdefault("connectionId", ctx.connection_id)

        out = self.SHC.handler_call(ctx.portfolio, ctx.org, extension, handler, params)
        ok = bool(out.get("success"))
        err = None if ok else out.get("output")
        if err is not None and not isinstance(err, str):
            try:
                err = json.dumps(err, default=str)[:2400]
            except Exception:
                err = str(err)[:2400]
        return ToolResult(
            tool_name=name,
            call_id=call_id,
            success=ok,
            result=out.get("output"),
            error=None if ok else (str(err) if err else "handler failed"),
        )

    def _run_delegation(
        self,
        args: dict[str, Any],
        call_id: Optional[str],
        session_id: str,
    ) -> ToolResult:
        del session_id
        assert self._profiles is not None
        assert self._models is not None
        assert self._profile is not None
        if not self._profile.supervisor:
            return ToolResult(
                tool_name="delegate_to_agent",
                call_id=call_id,
                success=False,
                result={},
                error="Only supervisor profiles may delegate",
            )
        target_id = str(args.get("agent_id") or "").strip()
        task = str(args.get("task") or "").strip()
        target = self._profiles.get(target_id)
        if not target.delegatable or target.id != target_id:
            return ToolResult(
                tool_name="delegate_to_agent",
                call_id=call_id,
                success=False,
                result={},
                error=f"Agent '{target_id}' is not delegatable",
            )

        shortlist = None if target.tool_allowlist == "all" else Profiles.allowlist_to_shortlist(
            target.tool_allowlist
        )
        if shortlist is not None and not shortlist:
            shortlist = None
        ctx = self._get_context()
        sub_tools = Tools(self.DAC, ctx.portfolio, ctx.org, shortlist=shortlist).list_tools()

        def _exec(name: str, a: dict[str, Any], cid: Optional[str]) -> dict[str, Any]:
            tr = self._execute_one_tool(name, a, cid, self._sessions.session_id if self._sessions else "")
            return {
                "success": tr.success,
                "result": tr.result,
                "error": tr.error,
                "proposed": tr.proposed,
                "approval_id": tr.approval_id,
            }

        answer = run_subagent_loop(
            profile=target,
            task=task,
            tools=sub_tools,
            models=self._models,
            execute_tool=_exec,
        )
        return ToolResult(
            tool_name="delegate_to_agent",
            call_id=call_id,
            success=True,
            result={"agent_id": target.id, "answer": answer},
        )

    def _execute_tool(self, state: AgentState) -> AgentState:
        messages = list(state.get("messages") or [])
        if not messages:
            return {}
        last = messages[-1]
        tool_calls = last.get("tool_calls") or []
        session_id = state["session_id"]

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except Exception:
                args = {}
            call_id = tc.get("id") or str(uuid.uuid4())

            self._save_event(
                SessionEvent(
                    event_id=str(uuid.uuid4()),
                    session_id=session_id,
                    event_type="tool_call",
                    timestamp=self._now(),
                    payload={"tool": name, "arguments": args, "call_id": call_id},
                )
            )

            tr = self._execute_one_tool(name, args, call_id, session_id)
            result_payload = {
                "tool": tr.tool_name,
                "call_id": tr.call_id,
                "success": tr.success,
                "result": tr.result,
                "error": tr.error,
                "proposed": tr.proposed,
                "approval_id": tr.approval_id,
            }
            self._save_event(
                SessionEvent(
                    event_id=str(uuid.uuid4()),
                    session_id=session_id,
                    event_type="tool_result",
                    timestamp=self._now(),
                    payload=result_payload,
                )
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(
                        {
                            "success": tr.success,
                            "output": tr.result,
                            "error": tr.error,
                            "proposed": tr.proposed,
                            "approval_id": tr.approval_id,
                        },
                        default=str,
                    )[:12000],
                }
            )

        # Refresh pending approvals for next LLM turn
        pending = self._approvals.list_pending(limit=10) if self._approvals else []
        return {"messages": messages, "pending_approvals": pending}

    def _grounding_gate(self, state: AgentState) -> AgentState:
        """Light backstop: empty final reply → ask model to answer; optional config flag."""
        assert self._ext_config is not None
        reply = (state.get("reply") or "").strip()
        retries = int(state.get("grounding_retries") or 0)
        if reply:
            return {}
        if not self._ext_config.grounding_enabled:
            return {"reply": "(No response generated.)"}
        if retries >= self._ext_config.max_grounding_retries:
            fallback = "I wasn't able to produce a final answer. Please try rephrasing."
            self._save_event(
                SessionEvent(
                    event_id=str(uuid.uuid4()),
                    session_id=state["session_id"],
                    event_type="assistant_message",
                    timestamp=self._now(),
                    payload={"text": fallback},
                )
            )
            return {"reply": fallback}

        messages = list(state.get("messages") or [])
        messages.append(
            {
                "role": "user",
                "content": (
                    "Your previous turn produced no user-visible answer. "
                    "Provide a concise final response now without calling tools "
                    "unless absolutely required."
                ),
                "_grounding_correction": True,
            }
        )
        return {
            "messages": messages,
            "grounding_retries": retries + 1,
            "reply": "",
        }
