"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";

import { SupportAgentConsole } from "../../components/support-agent-console";
import { login } from "../../lib/api";

const panelStyle: CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 28,
  boxShadow: "0 30px 80px rgba(35, 24, 11, 0.1)",
};

export default function SupportPage() {
  const [selectedUser, setSelectedUser] = useState("usr_alice");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [threadMode, setThreadMode] = useState<"ai" | "human">("ai");
  const [statusText, setStatusText] = useState("Preparing support desk...");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const traveler = params.get("traveler");
    if (traveler === "usr_alice" || traveler === "usr_bob") {
      setSelectedUser(traveler);
    }
  }, []);

  useEffect(() => {
    let active = true;

    async function boot() {
      try {
        const loginResponse = await login(selectedUser);
        if (!active) return;
        setThreadId(loginResponse.default_thread_id);
        setStatusText(selectedUser === "usr_alice" ? "Support desk connected to Alice." : "Support desk connected to Bob.");
      } catch (error) {
        if (!active) return;
        setStatusText(error instanceof Error ? error.message : "Unable to start support desk.");
      }
    }

    void boot();
    return () => {
      active = false;
    };
  }, [selectedUser]);

  return (
    <main
      style={{
        minHeight: "100vh",
        padding: "32px 20px 48px",
      }}
    >
      <div
        style={{
          maxWidth: 960,
          margin: "0 auto",
          display: "grid",
          gap: 22,
        }}
      >
        <section style={{ ...panelStyle, padding: "28px 28px 22px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "start", flexWrap: "wrap" }}>
            <div>
              <h1 style={{ fontSize: 36, lineHeight: 1.05, margin: 0 }}>Support Desk</h1>
              <p style={{ color: "var(--muted)", margin: "10px 0 0", maxWidth: 620 }}>
                Take over conversations, reply as a human agent, and hand the traveler back to AI when the issue is resolved.
              </p>
            </div>
            <div style={{ display: "grid", gap: 10, justifyItems: "end" }}>
              <div style={statusChipStyle(threadMode)}>{threadMode === "human" ? "Live Takeover" : "Standby"}</div>
              <label style={{ display: "grid", gap: 6, fontSize: 13, color: "var(--muted)" }}>
                <span>Traveler session</span>
                <select value={selectedUser} onChange={(event) => setSelectedUser(event.target.value)} style={selectStyle}>
                  <option value="usr_alice">Alice</option>
                  <option value="usr_bob">Bob</option>
                </select>
              </label>
            </div>
          </div>
        </section>

        <section style={{ ...panelStyle, padding: 20 }}>
          <SupportAgentConsole threadId={threadId} onStatus={setStatusText} onThreadModeChange={setThreadMode} />
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
    background: mode === "human" ? "rgba(143, 45, 45, 0.1)" : "rgba(31, 26, 20, 0.06)",
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
  minWidth: 160,
};
