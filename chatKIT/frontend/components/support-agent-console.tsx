"use client";

import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";

import { agentReturnToAi, agentSendMessage, agentTakeover, createHandoffWebSocket, type ChatMessage, type HandoffSocketEvent } from "../lib/api";

type SupportAgentConsoleProps = {
  threadId: string | null;
  onStatus: (message: string) => void;
  onThreadModeChange: (mode: "ai" | "human") => void;
};

export function SupportAgentConsole({ threadId, onStatus, onThreadModeChange }: SupportAgentConsoleProps) {
  const [agentName, setAgentName] = useState("Maya");
  const [message, setMessage] = useState("I can take over from here and help with the booking.");
  const [summary, setSummary] = useState("Handled clarification and collected the details needed to resume.");
  const [feed, setFeed] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!threadId) {
      setFeed([]);
      return;
    }

    const socket = createHandoffWebSocket(threadId, "agent");
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as HandoffSocketEvent;
      if (payload.event === "connected") {
        onThreadModeChange(payload.thread_mode);
      }
      if (payload.event === "user_message" || payload.event === "agent_message_echo") {
        setFeed((current) => [...current, payload.message]);
      }
      if (payload.event === "ai_resumed") {
        onThreadModeChange("ai");
        onStatus(payload.message);
      }
    };

    return () => {
      socket.close();
    };
  }, [threadId, onStatus, onThreadModeChange]);

  const recentFeed = useMemo(() => feed.slice(-8), [feed]);

  async function handleTakeover() {
    if (!threadId) return;
    setBusy(true);
    try {
      await agentTakeover(threadId, agentName);
      onThreadModeChange("human");
      onStatus("Support agent takeover activated over the dedicated WebSocket handoff channel.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSend() {
    if (!threadId || !message.trim()) return;
    setBusy(true);
    try {
      await agentSendMessage(threadId, agentName, message.trim());
      setMessage("");
      onStatus("Agent reply delivered over the handoff WebSocket path.");
    } finally {
      setBusy(false);
    }
  }

  async function handleReturn() {
    if (!threadId) return;
    setBusy(true);
    try {
      await agentReturnToAi(threadId, agentName, summary.trim());
      onThreadModeChange("ai");
      onStatus("Support handoff summary stored as hidden context and AI mode restored.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={panelStyle}>
      <div>
        <strong>Support Agent Console</strong>
        <p style={{ color: "var(--muted)", margin: "6px 0 0" }}>
          AI streaming stays on SSE. Human handoff messages use a dedicated WebSocket channel.
        </p>
      </div>

      <label style={fieldStyle}>
        <span>Agent name</span>
        <input value={agentName} onChange={(event) => setAgentName(event.target.value)} style={inputStyle} />
      </label>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button type="button" disabled={!threadId || busy} onClick={handleTakeover} style={primaryButtonStyle}>
          Take Over
        </button>
        <button type="button" disabled={!threadId || busy} onClick={handleReturn} style={secondaryButtonStyle}>
          Return to AI
        </button>
      </div>

      <label style={fieldStyle}>
        <span>Agent reply</span>
        <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={3} style={textAreaStyle} />
      </label>
      <button type="button" disabled={!threadId || busy || !message.trim()} onClick={handleSend} style={primaryButtonStyle}>
        Send Agent Message
      </button>

      <label style={fieldStyle}>
        <span>Resume summary</span>
        <textarea value={summary} onChange={(event) => setSummary(event.target.value)} rows={3} style={textAreaStyle} />
      </label>

      <div style={feedStyle}>
        {recentFeed.length === 0 ? (
          <div style={{ color: "var(--muted)" }}>No handoff messages yet.</div>
        ) : (
          recentFeed.map((item) => (
            <article key={item.id} style={bubbleStyle(item.role)}>
              <div style={{ fontSize: 12, color: "var(--muted)", textTransform: "uppercase", marginBottom: 6 }}>
                {item.role === "user" ? "User" : "Agent"}
              </div>
              <div>{String(item.content)}</div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

const panelStyle: CSSProperties = {
  display: "grid",
  gap: 14,
  border: "1px solid var(--border)",
  borderRadius: 24,
  padding: 18,
  background: "white",
  boxShadow: "0 24px 60px rgba(35, 24, 11, 0.08)",
};

const fieldStyle: CSSProperties = {
  display: "grid",
  gap: 8,
};

const inputStyle: CSSProperties = {
  borderRadius: 14,
  border: "1px solid var(--border)",
  padding: "10px 12px",
};

const textAreaStyle: CSSProperties = {
  borderRadius: 16,
  border: "1px solid var(--border)",
  padding: 12,
  resize: "vertical",
  font: "inherit",
};

const primaryButtonStyle: CSSProperties = {
  background: "var(--accent)",
  color: "white",
  border: "none",
  borderRadius: 999,
  padding: "11px 16px",
  cursor: "pointer",
};

const secondaryButtonStyle: CSSProperties = {
  background: "transparent",
  color: "var(--text)",
  border: "1px solid var(--border)",
  borderRadius: 999,
  padding: "11px 16px",
  cursor: "pointer",
};

const feedStyle: CSSProperties = {
  display: "grid",
  gap: 10,
  maxHeight: 260,
  overflowY: "auto",
};

const bubbleStyle = (role: "user" | "assistant" | "tool"): CSSProperties => ({
  borderRadius: 18,
  padding: 12,
  border: "1px solid var(--border)",
  background: role === "user" ? "#f6efe2" : "#eef8f4",
});
