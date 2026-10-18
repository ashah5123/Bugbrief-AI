import { useEffect, useState } from "react";
import { api } from "./types";
type Message = {
  id: string;
  visibility: string;
  author_role: string;
  author_name: string;
  body: string;
  created_at: string;
};
export default function Conversation({
  feedbackId,
  token,
}: {
  feedbackId?: string;
  token?: string;
}) {
  const endpoint = token
    ? `/public/submissions/${token}/messages`
    : `/feedback/${feedbackId}/messages`;
  const [messages, setMessages] = useState<Message[]>([]);
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState("public");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const refresh = () =>
      api<Message[]>(endpoint)
        .then((value) => {
          if (active) {
            setMessages(value);
            setError("");
            if (document.visibilityState === "visible" && document.hasFocus()) {
              api<{ changed: boolean }>(
                `/auth/notifications/${token ? "customer" : "company"}/read-report`,
                "POST",
                { report: token || feedbackId },
              )
                .then((result) => {
                  if (result.changed)
                    window.dispatchEvent(
                      new Event("bugbrief-notifications-updated"),
                    );
                })
                .catch(() => {});
            }
          }
        })
        .catch((e) => {
          if (active) {
            setMessages([]);
            setError(e.message);
          }
        });
    void refresh();
    const timer = window.setInterval(refresh, 15000);
    window.addEventListener("focus", refresh);
    window.addEventListener("bugbrief-reports-updated", refresh);
    return () => {
      active = false;
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("bugbrief-reports-updated", refresh);
    };
  }, [endpoint]);
  return (
    <section className="conversation-card" aria-label="Report conversation">
      <span className="eyebrow">KEEP THE DETAILS TOGETHER</span>
      <h3>Conversation</h3>
      <p>
        {token
          ? "Reply to the team here. Your replies stay with this report."
          : "Reply to the customer or leave a private note for your team."}
      </p>
      <div className="message-list" aria-live="polite">
        {!messages.length && (
          <p className="empty-conversation">
            No replies yet. Start the conversation below.
          </p>
        )}
        {messages.map((message) => (
          <article
            key={message.id}
            className={`report-message ${message.visibility === "internal" ? "internal-message" : ""}`}
          >
            <div>
              <strong>{message.author_name}</strong>
              <span>
                {message.visibility === "internal"
                  ? "Private · team only"
                  : message.author_role === "company"
                    ? "Company reply"
                    : "Customer reply"}
              </span>
            </div>
            <p>{message.body}</p>
            <time dateTime={message.created_at}>
              {new Date(message.created_at).toLocaleString()}
            </time>
          </article>
        ))}
      </div>
      <small>Showing up to 100 recent messages.</small>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          try {
            setMessages(
              await api<Message[]>(endpoint, "POST", { body, visibility }),
            );
            setBody("");
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {!token && (
          <label>
            Message visibility
            <select
              aria-label="Message visibility"
              value={visibility}
              disabled={busy}
              onChange={(event) => setVisibility(event.target.value)}
            >
              <option value="public">Reply to customer</option>
              <option value="internal">Private team note</option>
            </select>
          </label>
        )}
        <label>
          {visibility === "internal" ? "Private team note" : "Your reply"}
          <textarea
            required
            maxLength={4000}
            rows={3}
            value={body}
            disabled={busy}
            onChange={(event) => setBody(event.target.value)}
          />
        </label>
        <small>
          {visibility === "internal"
            ? "Only company employees and the workspace owner can see this note."
            : "This reply is visible to the customer and the company."}
        </small>
        {error && (
          <div className="alert error" role="alert">
            {error}
          </div>
        )}
        <button className="primary-button" disabled={busy || !body.trim()}>
          {busy
            ? "Saving…"
            : visibility === "internal"
              ? "Save private note"
              : "Send reply"}
        </button>
      </form>
    </section>
  );
}
