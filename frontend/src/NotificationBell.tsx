import { useEffect, useRef, useState } from "react";
import { Bell, X } from "lucide-react";
import { api } from "./types";
type Inbox = {
  items: {
    id: string;
    title: string;
    url: string;
    read_at: string | null;
    created_at: string;
  }[];
  unread_count: number;
  email_enabled: boolean;
  email_available: boolean;
  email_verified: boolean;
  mail_mode: string;
};
export default function NotificationBell({
  audience,
}: {
  audience: "company" | "customer";
}) {
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const revision = useRef(0);
  const preferencePending = useRef(false);
  const container = useRef<HTMLDivElement>(null);
  const endpoint = `/auth/notifications/${audience}`;
  async function refresh() {
    if (preferencePending.current) return;
    const version = ++revision.current;
    try {
      const value = await api<Inbox>(endpoint);
      if (version !== revision.current) return;
      setInbox(value);
      setError("");
    } catch (e) {
      if ((e as { status?: number }).status === 401) setInbox(null);
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(refresh, 15000);
    window.addEventListener("focus", refresh);
    window.addEventListener("bugbrief-notifications-updated", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("bugbrief-notifications-updated", refresh);
    };
  }, [endpoint]);
  useEffect(() => {
    function outside(event: PointerEvent) {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  if (!inbox) return null;
  return (
    <div className="notification-control" ref={container}>
      <button
        type="button"
        className="icon-button notification-toggle"
        aria-label={`Notifications${inbox.unread_count ? `, ${inbox.unread_count} unread` : ""}`}
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
          void refresh();
        }}
      >
        <Bell size={19} />
        {inbox.unread_count > 0 && (
          <span className="notification-count">
            {inbox.unread_count > 99 ? "99+" : inbox.unread_count}
          </span>
        )}
      </button>
      {open && (
        <section className="notification-inbox" aria-label="Notification inbox">
          <div className="notification-heading">
            <h3>Notifications</h3>
            <button
              className="icon-button"
              aria-label="Close notifications"
              onClick={() => setOpen(false)}
            >
              <X size={17} />
            </button>
          </div>
          <div className="notification-toolbar">
            <span>{inbox.unread_count} unread</span>
            <button
              className="text-button"
              disabled={busy || !inbox.unread_count}
              onClick={async () => {
                setBusy(true);
                try {
                  setInbox(await api<Inbox>(endpoint + "/read-all", "POST"));
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Mark all read
            </button>
          </div>
          {error && (
            <p className="alert error" role="alert">
              {error}
            </p>
          )}
          <div className="notification-list">
            {!inbox.items.length && (
              <p className="notification-empty">
                You’re all caught up. Replies and report updates will appear
                here.
              </p>
            )}
            {inbox.items.map((item) => (
              <a
                key={item.id}
                href={item.url}
                className={`notification-item ${!item.read_at ? "unread" : ""}`}
                onClick={async (event) => {
                  event.preventDefault();
                  setBusy(true);
                  try {
                    await api(endpoint + `/${item.id}/read`, "POST");
                    location.assign(item.url);
                  } catch (e) {
                    setError((e as Error).message);
                    setBusy(false);
                  }
                }}
              >
                <span className="notification-dot" />
                <span>
                  <strong>{item.title}</strong>
                  <time dateTime={item.created_at}>
                    {new Date(item.created_at).toLocaleString()}
                  </time>
                </span>
              </a>
            ))}
          </div>
          <div className="notification-preferences">
            <label>
              <input
                type="checkbox"
                checked={inbox.email_enabled}
                disabled={busy || !inbox.email_available}
                onChange={async (event) => {
                  const previous = inbox;
                  const enabled = event.target.checked;
                  revision.current += 1;
                  preferencePending.current = true;
                  setInbox({ ...inbox, email_enabled: enabled });
                  setBusy(true);
                  try {
                    setInbox(
                      await api<Inbox>(endpoint + "/preferences", "PATCH", {
                        email_enabled: enabled,
                      }),
                    );
                  } catch (e) {
                    setInbox(previous);
                    setError((e as Error).message);
                  } finally {
                    preferencePending.current = false;
                    setBusy(false);
                  }
                }}
              />
              Email alerts
            </label>
            <p>
              {!inbox.email_available
                ? "Sign in as an employee to enable email alerts for your account."
                : inbox.mail_mode === "local"
                  ? "Local testing: alerts appear in the owner’s test email outbox. No email is sent."
                  : !inbox.email_verified
                    ? "Verify your account email before enabling alerts."
                    : "Receive an email when someone replies or updates your report."}
            </p>
            <small>
              Showing the latest 50 alerts for projects you can access.
            </small>
          </div>
        </section>
      )}
    </div>
  );
}
