import { useEffect, useMemo, useState, type UIEvent } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { ChevronDown } from "lucide-react";

import ChatHistory from "@/components/console/chat-history";
import ChatInput from "@/components/console/chat-input";

interface AgentProps {
  portfolio: string;
  org: string;
  tool: string;
  tree?: { portfolios: Record<string, Portfolio> };
  onNavigate: (path: string) => void;
}

interface Portfolio {
  name: string;
  portfolio_id: string;
  orgs: Record<string, Org>;
  tools: Record<string, Tool>;
}

interface Org {
  name: string;
  org_id: string;
  tools: string[];
}

interface Tool {
  name: string;
  handle: string;
}

interface Message {
  author_id: string;
  time: number;
  is_active: boolean;
  context: Record<string, unknown>;
  events?: TurnEvent[];
  messages?: TurnEvent[];
  tool_invocations: unknown[];
  irn: string;
}

type TurnEvent = {
  _type?: string;
  type?: string;
  _out?: { role?: string; content?: unknown };
  out?: { role?: string; content?: unknown };
};

function turnEntries(message: Message): TurnEvent[] {
  const events = Array.isArray(message.events) ? message.events : [];
  const legacy = Array.isArray(message.messages) ? message.messages : [];
  if (events.length === 0) {
    return legacy;
  }
  const hasUserMessage = events.some((item) => eventType(item) === "user_message");
  if (hasUserMessage) {
    return events;
  }
  return [...legacy, ...events];
}

function parseStreamContent(item: TurnEvent): Record<string, unknown> | null {
  const out = (item._out ?? item.out) as { content?: unknown } | undefined;
  const raw = out?.content;
  if (raw == null) return null;
  if (typeof raw === "object" && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  if (typeof raw !== "string") return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/** Map Dumbo WebSocket debug envelopes to session roll rows the chat UI understands. */
function normalizeStreamUpdate(update: TurnEvent): TurnEvent {
  const type = eventType(update);
  if (type === "user_message" || type === "assistant_message" || type === "text") {
    return update;
  }

  const body = parseStreamContent(update);
  if (!body) {
    return update;
  }

  const channel = String(body.channel ?? "");
  const eventTypeName = String(body.event_type ?? "");

  if (channel === "dumbo_event" && eventTypeName === "inbound_message") {
    const payload = (body.payload ?? {}) as Record<string, unknown>;
    const text = String(payload.message ?? payload.text ?? "");
    return {
      _type: "user_message",
      _out: { role: "user", content: text },
    };
  }

  if (channel === "dumbo_event" && eventTypeName === "llm_response") {
    const payload = (body.payload ?? {}) as Record<string, unknown>;
    const text = String(payload.response_text ?? payload.message ?? payload.text ?? "");
    return {
      _type: "assistant_message",
      _out: { role: "assistant", content: text },
    };
  }

  if (channel === "dumbo_stream" && typeof body.message === "string") {
    return {
      _type: "assistant_message",
      _out: { role: "assistant", content: body.message },
    };
  }

  return update;
}

function rollDedupeKey(item: TurnEvent): string {
  const type = eventType(item) ?? "";
  const text = eventText(item);
  return `${type}:${text}`;
}

function eventType(item: TurnEvent): string | undefined {
  return (item._type ?? item.type) as string | undefined;
}

function eventText(item: TurnEvent): string {
  const out = (item._out ?? item.out) as { content?: unknown } | undefined;
  const raw = out?.content;
  if (raw == null) return "";
  if (typeof raw === "object") {
    try {
      return JSON.stringify(raw, null, 2);
    } catch {
      return String(raw);
    }
  }
  return String(raw);
}

export default function DumboChat({ portfolio, org, tool, tree, onNavigate }: AgentProps) {
  if (!sessionStorage.cu_handle) {
    onNavigate("/logout");
  }

  const entity_type = "dumbo-chat";
  const entity_id = useMemo(
    () => `dumbo-${org}-${sessionStorage.cu_handle ?? "anon"}`,
    [org]
  );

  const [threads, setThreads] = useState<{ items?: Array<{ _id: string; is_active?: boolean }> }>(
    {}
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeThread, setActiveThread] = useState<string | null>(null);
  const [refreshChat, setRefreshChat] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);

  useEffect(() => {
    const messageContainer = document.getElementById("dumboMessageContainer");
    if (messageContainer) {
      messageContainer.scrollTop = messageContainer.scrollHeight;
      setIsAtBottom(true);
    }
  }, [messages]);

  useEffect(() => {
    const fetchThreads = async () => {
      try {
        const response = await fetch(
          `${import.meta.env.VITE_API_URL}/_session/${portfolio}/${org}/${entity_type}/${entity_id}`,
          {
            method: "GET",
            headers: { Authorization: `Bearer ${sessionStorage.accessToken}` },
          }
        );
        const threadsList = await response.json();
        setThreads(threadsList);

        const activeT = threadsList.items?.find((thread: { is_active?: boolean }) => thread.is_active);

        if (activeT) {
          setActiveThread(activeT._id);
        } else {
          const newThreadResponse = await fetch(
            `${import.meta.env.VITE_API_URL}/_session/${portfolio}/${org}/${entity_type}/${entity_id}`,
            {
              method: "POST",
              headers: { Authorization: `Bearer ${sessionStorage.accessToken}` },
            }
          );
          const { success, document } = await newThreadResponse.json();
          if (success) {
            setActiveThread(document._id);
          }
        }
      } catch (error) {
        console.error("Error fetching Dumbo threads:", error);
      }
    };

    fetchThreads();
  }, [org, portfolio, entity_type, entity_id]);

  useEffect(() => {
    const fetchMessages = async () => {
      if (!activeThread) return;

      try {
        const response = await fetch(
          `${import.meta.env.VITE_API_URL}/_session/${portfolio}/${org}/${entity_type}/${entity_id}/${activeThread}/messages`,
          {
            method: "GET",
            headers: { Authorization: `Bearer ${sessionStorage.accessToken}` },
          }
        );
        const messagesList = await response.json();
        setMessages(messagesList.items ?? []);
      } catch (error) {
        console.error("Error fetching Dumbo messages:", error);
      }
    };

    fetchMessages();
  }, [activeThread, refreshChat, portfolio, org, entity_type, entity_id]);

  const messageAction = (msg: Record<string, unknown>) => {
    if (msg.type === "rq") {
      const doc = msg.doc as Message;
      setMessages((prev) => [...prev, doc]);
      return;
    }

    if (msg.type === "rs") {
      const update = normalizeStreamUpdate(msg.update as TurnEvent);
      if (!update || (!("out" in update) && !("_out" in update))) {
        return;
      }
      setMessages((prev) => {
        if (prev.length === 0) return prev;
        const lastMessage = prev[prev.length - 1];
        const baseEvents = Array.isArray(lastMessage.events) ? lastMessage.events : [];
        const normalizedType = eventType(update);
        const key = rollDedupeKey(update);
        const alreadyPresent = baseEvents.some((item) => rollDedupeKey(item) === key);
        if (alreadyPresent && (normalizedType === "user_message" || normalizedType === "assistant_message")) {
          return prev;
        }
        const updatedLastMessage = {
          ...lastMessage,
          events: [...baseEvents, update],
        };
        return [...prev.slice(0, -1), updatedLastMessage];
      });
      return;
    }

    if (msg.type === "refresh_chat") {
      setRefreshChat((prev) => !prev);
    }
  };

  const threadAction = async (switchThread: string) => {
    if (switchThread === "new_thread") {
      const newThreadResponse = await fetch(
        `${import.meta.env.VITE_API_URL}/_session/${portfolio}/${org}/${entity_type}/${entity_id}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${sessionStorage.accessToken}` },
        }
      );
      const { success, document } = await newThreadResponse.json();
      if (success) {
        setMessages([]);
        setActiveThread(document._id);
      }
    } else {
      setMessages([]);
      setActiveThread(switchThread);
    }
  };

  const payloadChatMessage = {
    action: "chat_message",
    portfolio,
    org,
    entity_type,
    entity_id,
    core: "dumbo/generic_agent",
    thread: activeThread,
  };

  const captionChatInput = {
    portfolio_name: tree?.portfolios[portfolio]?.name,
    org_name: tree?.portfolios[portfolio]?.orgs[org]?.name,
    tool_name: tool ? tree?.portfolios[portfolio]?.tools[tool]?.name : undefined,
    activeThread,
    hint: "Message the Dumbo agent…",
  };

  const handleScroll = (e: UIEvent<HTMLDivElement>) => {
    const bottom =
      Math.abs(
        e.currentTarget.scrollHeight - e.currentTarget.scrollTop - e.currentTarget.clientHeight
      ) < 1;
    setIsAtBottom(bottom);
  };

  const renderTurnEvent = (item: TurnEvent, idx: number) => {
    const type = eventType(item);
    const text = eventText(item);

    if (type === "user_message") {
      return (
        <div
          key={idx}
          className="mb-2 flex max-w-[80%] flex-col self-end rounded-xl bg-muted p-4"
        >
          {text}
        </div>
      );
    }

    if (type === "assistant_message") {
      return (
        <div
          key={idx}
          className="mb-2 flex max-w-[80%] flex-col self-start rounded-xl bg-primary/10 p-4"
        >
          {text}
        </div>
      );
    }

    if (
      type === "dumbo_stream" ||
      type === "dumbo_event" ||
      type === "tool_call" ||
      type === "tool_result" ||
      type === "dumbo_approval"
    ) {
      let body = text;
      const raw = (item._out ?? item.out)?.content;
      if (typeof raw === "string") {
        try {
          body = JSON.stringify(JSON.parse(raw), null, 2);
        } catch {
          body = raw;
        }
      } else if (raw && typeof raw === "object") {
        try {
          body = JSON.stringify(raw, null, 2);
        } catch {
          body = String(raw);
        }
      }
      return (
        <div
          key={idx}
          className="mb-2 max-w-[95%] self-start rounded-md border border-dashed bg-muted/20 p-2 font-mono text-xs text-muted-foreground"
        >
          <div className="mb-1 text-[10px] uppercase tracking-wide opacity-80">{type}</div>
          <pre className="whitespace-pre-wrap break-words">{body}</pre>
        </div>
      );
    }

    if (type === "text") {
      return (
        <div
          key={idx}
          className="mb-2 flex max-w-[80%] flex-col self-end rounded-xl bg-muted/80 p-3 text-sm"
        >
          {text}
        </div>
      );
    }

    if (!type) return null;

    return (
      <div
        key={idx}
        className="mb-2 max-w-[95%] self-start rounded-md border bg-muted/30 p-2 font-mono text-xs text-muted-foreground"
      >
        <div className="mb-1 text-[10px] uppercase tracking-wide opacity-80">{type}</div>
        <pre className="whitespace-pre-wrap break-words">{text}</pre>
      </div>
    );
  };

  return (
    <PanelGroup direction="horizontal">
      <Panel defaultSize={97} minSize={70}>
        <span className="flex h-[calc(100vh-80px)] flex-col rounded-t-none">
          <span className="relative flex min-h-0 flex-1 flex-col">
            <div className="pointer-events-none absolute left-0 right-0 top-0 z-10 h-8 shadow-[inset_0_20px_20px_-10px_rgba(0,0,0,0.3)]" />

            <div
              className="relative flex-1 overflow-y-auto px-4 sm:px-6"
              id="dumboMessageContainer"
              onScroll={handleScroll}
            >
              <div className="relative">
                {activeThread &&
                  messages.map((m, index) => (
                    <div key={index} className="mb-4 flex flex-col">
                      <div className="mb-2 mt-4 text-center text-sm text-muted-foreground">
                        {m?.time
                          ? new Date(m.time * 1000)
                              .toLocaleString("en-US", {
                                weekday: "short",
                                month: "short",
                                day: "numeric",
                                hour: "numeric",
                                minute: "2-digit",
                                hour12: true,
                              })
                              .replace(/(\w+)\s+(\w+)\s+(\d+)\s+at/, "$1, $2 $3 at")
                          : ""}
                      </div>
                      <div className="flex flex-col">
                        {turnEntries(m).map((item, idx) => renderTurnEvent(item, idx))}
                      </div>
                    </div>
                  ))}
              </div>

              <div className="sticky bottom-0 left-0 right-0 z-20 h-6">
                <div className="pointer-events-none h-full bg-gradient-to-t from-background via-background/20 to-transparent" />
                {!isAtBottom && (
                  <div
                    className="absolute bottom-2 left-1/2 -translate-x-1/2 transform cursor-pointer text-muted-foreground animate-bounce hover:text-foreground"
                    onClick={() => {
                      document.getElementById("dumboMessageContainer")?.scrollTo({
                        top: document.getElementById("dumboMessageContainer")?.scrollHeight,
                        behavior: "smooth",
                      });
                    }}
                  >
                    <ChevronDown className="h-5 w-5" />
                  </div>
                )}
              </div>
            </div>

            {activeThread && (
              <div className="flex flex-col gap-0">
                <ChatInput
                  messageUp={messageAction}
                  payload={payloadChatMessage}
                  captions={captionChatInput}
                />
              </div>
            )}
          </span>
        </span>
      </Panel>

      <PanelResizeHandle className="w-1 bg-border transition-colors hover:bg-primary/50" />

      <Panel defaultSize={3} minSize={3} maxSize={20}>
        <span className="flex h-[calc(100vh-80px)] flex-col overflow-y-auto border-l">
          <ChatHistory history={threads} actionUp={threadAction} />
        </span>
      </Panel>
    </PanelGroup>
  );
}
