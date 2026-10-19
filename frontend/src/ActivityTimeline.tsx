import { useEffect, useRef, useState } from "react";
import { Clock3 } from "lucide-react";
import { api, ApiError } from "./types";

export type ActivityEvent = { id: string; label: string; note: string; created_at: string; actor_name?: string | null; actor_role?: string | null };
export type ActivityPage = { items: ActivityEvent[]; next_before: string | null };
const merge = (old: ActivityEvent[], incoming: ActivityEvent[]) => {
  const values = [...new Map([...old, ...incoming].map(event => [event.id, event])).values()];
  return values.filter(event => event.id !== "received" || values.length === 1)
    .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
};

export default function ActivityTimeline({ endpoint, initial, refreshKey, title = "Progress history" }: {
  endpoint: string; initial?: ActivityPage; refreshKey?: unknown; title?: string;
}) {
  const [events, setEvents] = useState<ActivityEvent[]>(initial?.items || []);
  const cache = useRef(initial?.items || []);
  const [cursor, setCursor] = useState<string | null>(initial?.next_before || null);
  const cursorRef = useRef(initial?.next_before || null);
  const started = useRef(!!initial);
  const epoch = useRef(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  function acceptLatest(page: ActivityPage) {
    const ids = new Set(cache.current.map(event => event.id));
    const gap = ids.size > 0 && page.items.length > 0 && !page.items.some(event => ids.has(event.id));
    if (!started.current || gap) {
      cache.current = page.items;
      cursorRef.current = page.next_before; setCursor(page.next_before);
      if (gap) { epoch.current += 1; setNotice("Newer updates arrived. Load older updates again to see the complete history."); }
    } else cache.current = merge(cache.current, page.items);
    started.current = true; setEvents(cache.current); setError("");
  }
  useEffect(() => {
    if (initial) acceptLatest(initial);
  }, [initial]);
  useEffect(() => {
    let live = true;
    const refresh = () => api<ActivityPage>(endpoint).then(value => { if (live) acceptLatest(value); }).catch(e => {
      if (!live) return;
      setError(e.message);
      if (e instanceof ApiError && [401, 403, 404].includes(e.status)) {
        epoch.current += 1; cache.current = []; setEvents([]); cursorRef.current = null; setCursor(null); started.current = false;
      }
    });
    if (!initial) void refresh();
    const focus = () => { void refresh(); };
    const timer = window.setInterval(focus, 15000);
    window.addEventListener("focus", focus);
    return () => { live = false; epoch.current += 1; clearInterval(timer); window.removeEventListener("focus", focus); };
  }, [endpoint, refreshKey]);
  async function loadOlder() {
    if (!cursorRef.current || busy) return;
    const currentEpoch = epoch.current;
    setBusy(true); setError("");
    try {
      const page = await api<ActivityPage>(`${endpoint}?before=${encodeURIComponent(cursorRef.current)}`);
      if (currentEpoch !== epoch.current) return;
      cache.current = merge(cache.current, page.items); setEvents(cache.current);
      cursorRef.current = page.next_before; setCursor(page.next_before);
    } catch (e) {
      if (currentEpoch !== epoch.current) return;
      setError((e as Error).message);
      if (e instanceof ApiError && [401, 403, 404].includes(e.status)) {
        cache.current = []; setEvents([]); cursorRef.current = null; setCursor(null); started.current = false;
      }
    } finally { setBusy(false); }
  }
  return <section className="progress-timeline" aria-label={title}>
    <h4><Clock3 size={14} />{title}</h4>
    <small>{events.length} update{events.length === 1 ? "" : "s"} loaded{cursor ? " · Earlier updates available" : ""}.</small>
    {notice && <p role="status">{notice}</p>}
    {error && <div className="alert error" role="alert">{error}</div>}
    {!events.length && !error && <p>No recorded updates yet.</p>}
    <ol>{[...events].reverse().map(event => <li key={event.id}>
      <span className="timeline-dot" /><div><strong>{event.label}</strong>
        <span className="activity-actor">{event.actor_name ? `By ${event.actor_name}${event.actor_role ? ` · ${event.actor_role === "owner" ? "Workspace owner" : event.actor_role}` : ""}` : "Actor not recorded"}</span>
        <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time>
        {event.note && <p>{event.note}</p>}
      </div>
    </li>)}</ol>
    {cursor && <button className="secondary-button" type="button" disabled={busy || !!error} onClick={() => void loadOlder()}>{busy ? "Loading earlier updates…" : "Load older updates"}</button>}
  </section>;
}
