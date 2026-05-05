export type DemoLoginResponse = {
  user_id: string;
  thread_ids: string[];
  default_thread_id: string;
};

export type SessionResponse = {
  client_secret: string;
  expires_at: number;
  thread_id: string;
  session_id: string;
};

export type ChatMessage = {
  id: string;
  thread_id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  timestamp: number;
  status: "delivered" | "streaming" | "failed" | "cancelled";
  hidden: boolean;
};

export type WidgetActionSchema = {
  id: string;
  label: string;
  style: "primary" | "secondary";
};

export type WidgetSchema = {
  id: string;
  type: string;
  data: Record<string, unknown>;
  actions: WidgetActionSchema[];
  expires_at: number;
  state: "idle" | "loading" | "success" | "error";
  version: number;
};

export type ThreadMessagesResponse = {
  messages: ChatMessage[];
  widgets: WidgetSchema[];
  thread_mode: "ai" | "human";
};

export type ActionResponse = {
  assistant_message: ChatMessage | null;
  widget: WidgetSchema | null;
  widget_id: string;
  action_id: string;
};

export type StreamEvent =
  | { event: "status"; data: { status: "submitted" | "streaming"; stream_id: string; message_id?: string } }
  | { event: "token"; data: { delta: string; stream_id: string } }
  | { event: "assistant_message"; data: { stream_id: string; message: ChatMessage } }
  | { event: "widget"; data: WidgetSchema }
  | { event: "human_mode"; data: { thread_mode: "human"; message: string } }
  | { event: "stream_end"; data: { status: "ready"; stream_id: string } }
  | { event: "cancelled"; data: { stream_id: string; message_id: string; content: string; status: "cancelled" } };

export type HandoffSocketEvent =
  | { event: "connected"; thread_id: string; role: "user" | "agent"; thread_mode: "ai" | "human" }
  | { event: "agent_joined"; thread_id: string; agent_name: string; thread_mode: "human"; message: string }
  | { event: "human_agent_message"; thread_id: string; agent_name: string; message: ChatMessage }
  | { event: "agent_message_echo"; thread_id: string; agent_name: string; message: ChatMessage }
  | { event: "user_message"; thread_id: string; message: ChatMessage }
  | { event: "ai_resumed"; thread_id: string; thread_mode: "ai"; message: string };

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.clone().json() as { detail?: string };
      detail = payload.detail ?? "";
    } catch {
      detail = "";
    }

    const message = response.status === 403
      ? "You do not have access to this conversation."
      : response.status === 404
        ? "This conversation no longer exists."
        : response.status === 410
          ? "This offer is no longer available. Search again?"
          : response.status === 422
            ? (detail || "The widget payload was invalid.")
            : response.status === 409
              ? (detail || "This action was already completed.")
              : response.status === 401
                ? "Authentication failed."
                : (detail || "Request failed.");
    const error = new Error(message);
    (error as Error & { status?: number }).status = response.status;
    throw error;
  }

  return response.json() as Promise<T>;
}

export function login(userId: string) {
  return request<DemoLoginResponse>("/api/dev/login", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export function bootstrapSession(threadId: string) {
  return request<SessionResponse>("/api/session", {
    method: "POST",
    body: JSON.stringify({ thread_id: threadId }),
  });
}

export function refreshSession(threadId: string) {
  return request<SessionResponse>("/api/session/refresh", {
    method: "POST",
    body: JSON.stringify({ thread_id: threadId }),
  });
}

export function fetchThreadState(threadId: string) {
  return request<ThreadMessagesResponse>(`/api/thread/${threadId}/messages`);
}

export function sendWidgetAction(payload: {
  threadId: string;
  clientSecret: string;
  widgetId: string;
  actionId: string;
  payload?: Record<string, unknown>;
}) {
  return request<ActionResponse>("/api/actions", {
    method: "POST",
    body: JSON.stringify({
      thread_id: payload.threadId,
      client_secret: payload.clientSecret,
      widget_id: payload.widgetId,
      action_id: payload.actionId,
      payload: payload.payload ?? {},
    }),
  });
}

export function agentTakeover(threadId: string, agentName: string) {
  return agentRequest<{ thread_id: string; thread_mode: "human"; agent_name: string }>("/api/agent/takeover", {
    thread_id: threadId,
    agent_name: agentName,
  });
}

export function agentSendMessage(threadId: string, agentName: string, text: string) {
  return agentRequest<{ status: string; message: ChatMessage }>("/api/agent/message", {
    thread_id: threadId,
    agent_name: agentName,
    text,
  });
}

export function agentReturnToAi(threadId: string, agentName: string, summary: string) {
  return agentRequest<{ thread_id: string; thread_mode: "ai" }>("/api/agent/return-to-ai", {
    thread_id: threadId,
    agent_name: agentName,
    summary,
  });
}

export async function cancelStream(threadId: string, streamId: string) {
  return request<{ stream_id: string; status: string }>("/api/chat/cancel", {
    method: "POST",
    body: JSON.stringify({ thread_id: threadId, stream_id: streamId }),
  });
}

export async function streamChatMessage(payload: {
  threadId: string;
  clientSecret: string;
  text: string;
  onEvent: (event: StreamEvent) => void;
}) {
  const response = await fetch(`${API_BASE}/api/chat/message`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      thread_id: payload.threadId,
      client_secret: payload.clientSecret,
      text: payload.text,
    }),
  });

  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || "Unable to start stream.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const parsed = parseSseChunk(chunk);
      if (parsed) {
        payload.onEvent(parsed);
      }
    }
  }
}

function parseSseChunk(chunk: string): StreamEvent | null {
  const lines = chunk.split("\n");
  const eventLine = lines.find((line) => line.startsWith("event: "));
  const dataLine = lines.find((line) => line.startsWith("data: "));
  if (!eventLine || !dataLine) return null;

  const event = eventLine.replace("event: ", "").trim();
  const data = JSON.parse(dataLine.replace("data: ", ""));
  return { event, data } as StreamEvent;
}

function agentRequest<T>(path: string, body: Record<string, unknown>) {
  const agentKey = process.env.NEXT_PUBLIC_AGENT_DEMO_KEY ?? "demo-agent-key";
  return request<T>(path, {
    method: "POST",
    headers: {
      "x-agent-key": agentKey,
    },
    body: JSON.stringify(body),
  });
}

export function createHandoffWebSocket(threadId: string, role: "user" | "agent"): WebSocket {
  const wsBase = API_BASE.replace(/^http/, "ws");
  const agentKey = process.env.NEXT_PUBLIC_AGENT_DEMO_KEY ?? "demo-agent-key";
  const suffix = role === "agent" ? `?role=agent&agent_key=${encodeURIComponent(agentKey)}` : "?role=user";
  return new WebSocket(`${wsBase}/ws/handoff/${threadId}${suffix}`);
}
