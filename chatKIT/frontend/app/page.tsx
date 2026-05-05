"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { TravelChatPanel } from "../components/travel-chat-panel";
import { bootstrapSession, login, refreshSession, type SessionResponse } from "../lib/api";

const panelStyle: CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 28,
  boxShadow: "0 30px 80px rgba(35, 24, 11, 0.1)",
};

export default function HomePage() {
  const [selectedUser, setSelectedUser] = useState("usr_alice");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [statusText, setStatusText] = useState("Preparing your travel assistant...");
  const [threadMode, setThreadMode] = useState<"ai" | "human">("ai");
  const [booting, setBooting] = useState(true);
  useEffect(() => {
    let active = true;

    async function boot() {
      try {
        const loginResponse = await login(selectedUser);
        if (!active) return;
        const nextThreadId = loginResponse.default_thread_id;
        setThreadId(nextThreadId);

        const nextSession = await bootstrapSession(nextThreadId);
        if (!active) return;
        setSession(nextSession);
        setStatusText(selectedUser === "usr_alice" ? "Welcome back, Alice." : "Welcome back, Bob.");
      } catch (error) {
        if (!active) return;
        setStatusText(error instanceof Error ? error.message : "Unable to start the assistant.");
      } finally {
        if (active) {
          setBooting(false);
        }
      }
    }

    void boot();
    return () => {
      active = false;
    };
  }, [selectedUser]);

  useEffect(() => {
    let active = true;

    async function syncThreadSession() {
      if (!threadId || !session || session.thread_id === threadId) {
        return;
      }
      try {
        const refreshed = await refreshSession(threadId);
        if (!active) return;
        setSession(refreshed);
      } catch (error) {
        if (!active) return;
        setStatusText(error instanceof Error ? error.message : "Unable to refresh the conversation session.");
      }
    }

    void syncThreadSession();
    return () => {
      active = false;
    };
  }, [session, threadId]);

  async function getClientSecret(existing?: string) {
    if (!threadId) {
      throw new Error("No active conversation.");
    }
    if (!session) {
      const nextSession = await bootstrapSession(threadId);
      setSession(nextSession);
      return nextSession.client_secret;
    }
    const now = Math.floor(Date.now() / 1000);
    if (existing && session.expires_at - now > 300) {
      return existing;
    }
    const refreshed = await refreshSession(threadId);
    setSession(refreshed);
    return refreshed.client_secret;
  }

  return (
    <main
      style={{
        minHeight: "100vh",
        padding: "32px 20px 48px",
      }}
    >
      <div
        style={{
          maxWidth: 1120,
          margin: "0 auto",
          display: "grid",
          gap: 22,
        }}
      >
        <section style={{ ...panelStyle, padding: "28px 28px 22px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "start", flexWrap: "wrap" }}>
            <div>
              <h1 style={{ fontSize: 38, lineHeight: 1.05, margin: 0 }}>Travel Booking AI</h1>
              <p style={{ color: "var(--muted)", margin: "10px 0 0", maxWidth: 720 }}>
                Plan routes, compare options, and move from search to booking in one conversation.
              </p>
            </div>
            <div style={{ display: "grid", gap: 10, justifyItems: "end" }}>
              <div style={statusChipStyle(threadMode)}>
                {threadMode === "human" ? "Support Agent Connected" : booting ? "Starting" : "AI Ready"}
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "end" }}>
                <label style={{ display: "grid", gap: 6, fontSize: 13, color: "var(--muted)" }}>
                  <span>Traveler</span>
                  <select value={selectedUser} onChange={(event) => setSelectedUser(event.target.value)} style={selectStyle}>
                    <option value="usr_alice">Alice</option>
                    <option value="usr_bob">Bob</option>
                  </select>
                </label>
                <div style={{ display: "grid", gap: 6, fontSize: 13, color: "var(--muted)" }}>
                  <span>Support</span>
                  <a href={`/support?traveler=${encodeURIComponent(selectedUser)}`} target="_blank" rel="noreferrer" style={supportLinkStyle(threadMode)}>
                    {threadMode === "human" ? "Open Support Desk" : "Support Desk"}
                  </a>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section style={{ ...panelStyle, padding: 20 }}>
          <TravelChatPanel
            session={session}
            threadId={threadId}
            selectedUser={selectedUser}
            getClientSecret={getClientSecret}
            onStatus={setStatusText}
            threadMode={threadMode}
            onThreadModeChange={setThreadMode}
            onThreadIdChange={setThreadId}
          />
        </section>

        <section
          style={{
            ...panelStyle,
            padding: "14px 18px",
            color: "var(--muted)",
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <span>{statusText}</span>
          {threadId ? <span>Conversation: {threadId.replace("thread_", "").replaceAll("_", " ")}</span> : null}
        </section>
      </div>
    </main>
  );
}

function statusChipStyle(mode: "ai" | "human"): CSSProperties {
  return {
    borderRadius: 999,
    padding: "10px 14px",
    background: mode === "human" ? "rgba(143, 45, 45, 0.1)" : "rgba(11, 110, 79, 0.12)",
    color: "var(--text)",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: "0.02em",
  };
}

const selectStyle: CSSProperties = {
  borderRadius: 14,
  border: "1px solid var(--border)",
  padding: "10px 12px",
  background: "white",
  minWidth: 140,
};

function supportLinkStyle(mode: "ai" | "human"): CSSProperties {
  return {
    borderRadius: 14,
    border: mode === "human" ? "1px solid rgba(143, 45, 45, 0.2)" : "1px solid var(--border)",
    padding: "10px 12px",
    background: mode === "human" ? "rgba(143, 45, 45, 0.08)" : "white",
    color: "var(--text)",
    textDecoration: "none",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    minWidth: 160,
    fontWeight: 600,
  };
}
