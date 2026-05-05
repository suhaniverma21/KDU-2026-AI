"use client";

import type { CSSProperties } from "react";
import { useEffect } from "react";
import { ChatKit, useChatKit } from "@openai/chatkit-react";

import { createHandoffWebSocket, type HandoffSocketEvent, type SessionResponse } from "../lib/api";

type TravelChatPanelProps = {
  session: SessionResponse | null;
  threadId: string | null;
  selectedUser: string;
  getClientSecret: (existing?: string) => Promise<string>;
  onStatus: (message: string) => void;
  threadMode: "ai" | "human";
  onThreadModeChange: (mode: "ai" | "human") => void;
  onThreadIdChange: (threadId: string | null) => void;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const DOMAIN_KEY = process.env.NEXT_PUBLIC_CHATKIT_DOMAIN_KEY ?? "travel-booking-local";

export function TravelChatPanel({
  session,
  threadId,
  selectedUser,
  getClientSecret,
  onStatus,
  threadMode,
  onThreadModeChange,
  onThreadIdChange,
}: TravelChatPanelProps) {
  const chat = useChatKit({
    api: {
      url: `${API_BASE}/api/chatkit`,
      domainKey: DOMAIN_KEY,
      fetch: async (input, init) => {
        await getClientSecret(session?.client_secret);
        return fetch(input, {
          ...init,
          credentials: "include",
        });
      },
    },
    initialThread: threadId,
    theme: {
      colorScheme: "light",
      radius: "round",
      density: "compact",
      color: {
        accent: {
          primary: "#0f766e",
          level: 2,
        },
      },
      typography: {
        fontFamily: "'Segoe UI', 'Helvetica Neue', sans-serif",
      },
    },
    header: {
      title: {
        enabled: true,
        text: threadMode === "human" ? "Travel Support" : "Travel Booking AI",
      },
      rightAction: {
        icon: "history",
        onClick: () => {
          window.open(`/support?traveler=${encodeURIComponent(selectedUser)}`, "_blank", "noopener,noreferrer");
        },
      },
    },
    history: {
      enabled: true,
      showDelete: false,
      showRename: false,
    },
    composer: {
      placeholder: threadMode === "human" ? "Write to the support agent..." : "Ask about a trip, flight, or booking...",
    },
    startScreen: {
      greeting: "Where would you like to travel next?",
      prompts: [
        { label: "Low-cost flight", prompt: "Find me a low-cost flight option for my trip." },
        { label: "Weekend trip", prompt: "Plan a weekend trip and show one booking option." },
      ],
    },
    onReady: () => {
      onStatus("Travel assistant ready.");
    },
    onResponseStart: () => {
      onStatus(threadMode === "human" ? "Routing your message to support..." : "Streaming response...");
    },
    onResponseEnd: () => {
      onStatus(threadMode === "human" ? "Support message sent." : "Response received.");
    },
    onError: ({ error }) => {
      onStatus(error?.message ?? "Something went wrong.");
    },
    onThreadChange: ({ threadId: nextThreadId }) => {
      onThreadIdChange(nextThreadId);
    },
  });

  useEffect(() => {
    if (!threadId) {
      return;
    }

    const socket = createHandoffWebSocket(threadId, "user");
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as HandoffSocketEvent;
      if (payload.event === "connected") {
        onThreadModeChange(payload.thread_mode);
      }
      if (payload.event === "agent_joined") {
        onThreadModeChange("human");
        onStatus(payload.message);
      }
      if (payload.event === "human_agent_message") {
        void chat.fetchUpdates();
        onStatus(`${payload.agent_name} replied.`);
      }
      if (payload.event === "ai_resumed") {
        onThreadModeChange("ai");
        onStatus(payload.message);
        void chat.fetchUpdates();
      }
    };

    return () => {
      socket.close();
    };
  }, [chat, onStatus, onThreadModeChange, threadId]);

  return (
    <section style={panelStyle}>
      <div style={headerStyle}>
        <div>
          <strong style={{ fontSize: 20 }}>Chat</strong>
          <p style={{ margin: "6px 0 0", color: "var(--muted)" }}>
            Ask about flights, routes, prices, or booking options.
          </p>
        </div>
        <div style={modeBadgeStyle(threadMode)}>{threadMode === "human" ? "Support Agent" : "AI Assistant"}</div>
      </div>

      <div style={frameShellStyle}>
        <ChatKit
          key={threadId ?? "new-thread"}
          control={chat.control}
          style={{
            width: "100%",
            height: 640,
            display: "block",
            border: "none",
            borderRadius: 22,
            overflow: "hidden",
            background: "white",
          }}
        />
      </div>
    </section>
  );
}

const panelStyle: CSSProperties = {
  display: "grid",
  gap: 16,
};

const headerStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "start",
  gap: 16,
  flexWrap: "wrap",
};

const frameShellStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 24,
  overflow: "hidden",
  background: "white",
};

const modeBadgeStyle = (mode: "ai" | "human"): CSSProperties => ({
  borderRadius: 999,
  padding: "8px 12px",
  background: mode === "human" ? "rgba(143, 45, 45, 0.1)" : "rgba(11, 110, 79, 0.14)",
  color: "var(--text)",
  fontSize: 13,
  fontWeight: 600,
});
