"use client";

import { useState } from "react";
import { askFollowUp } from "@/lib/api";
import { ApiError, ChatMessage } from "@/lib/types";

interface ChatPanelProps {
  analysisId: string;
  sessionId: string;
}

export default function ChatPanel({ analysisId, sessionId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isLoading) return;

    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setQuestion("");
    setIsLoading(true);

    try {
      const res = await askFollowUp(analysisId, sessionId, trimmed);
      setMessages((prev) => [...prev, { role: "assistant", content: res.answer }]);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Something went wrong answering that question.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="chat-panel">
      <h2 className="chat-title">Ask about this report</h2>

      {messages.length > 0 && (
        <div className="chat-messages">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`chat-message ${
                msg.role === "user" ? "chat-message-user" : "chat-message-assistant"
              }`}
            >
              <span className="chat-message-role">
                {msg.role === "user" ? "You" : "MediScan"}
              </span>
              <p className="chat-message-content">{msg.content}</p>
            </div>
          ))}
        </div>
      )}

      {isLoading && <p className="chat-loading">Thinking&hellip;</p>}
      {error && <p className="chat-error">{error}</p>}

      <form className="chat-input-row" onSubmit={handleSubmit}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. What does the hemoglobin value mean for me?"
          className="chat-input"
          disabled={isLoading}
          maxLength={2000}
        />
        <button
          type="submit"
          className="chat-submit"
          disabled={isLoading || !question.trim()}
        >
          Ask
        </button>
      </form>
    </div>
  );
}
