import { useEffect, useRef, useState } from "react";
import { ImagePlus, X } from "lucide-react";
import { api, ApiError } from "./types";
import ScreenshotReview from "./ScreenshotReview";
type ReplyImage = {
  id: string; filename: string; caption: string; mime_type: string; size: number; width: number; height: number;
};
type PendingImage = { key: string; filename: string; caption: string; mime_type: string; content_base64: string; reviewed: true; preview: string };
type Message = {
  id: string; visibility: string; author_role: string; author_name: string; body: string; created_at: string;
  attachments: ReplyImage[];
};
function base64(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(new Error("Could not prepare screenshot. Please choose it again."));
    reader.readAsDataURL(blob);
  });
}
type MessagePage = { items: Message[]; next_before: string | null };
function mergeMessages(previous: Message[], incoming: Message[]) {
  return [...new Map([...previous, ...incoming].map(value => [value.id, value])).values()]
    .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
}
export default function Conversation({ feedbackId, token, readOnly = false }: { feedbackId?: string; token?: string; readOnly?: boolean }) {
  const endpoint = token ? `/public/submissions/${token}/messages` : `/feedback/${feedbackId}/messages`;
  const [messages, setMessages] = useState<Message[]>([]);
  const messageCache = useRef<Message[]>([]);
  const [historyNotice, setHistoryNotice] = useState("");
  const [older, setOlder] = useState<string | null>(null);
  const olderRef = useRef<string | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const generation = useRef(0);
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState("public");
  const [busy, setBusy] = useState(false);
  const [readError, setReadError] = useState("");
  const [sendError, setSendError] = useState("");
  const [images, setImages] = useState<PendingImage[]>([]);
  const [reviewOpen, setReviewOpen] = useState(false);
  const previews = useRef(new Set<string>());
  const pending = useRef<{ signature: string; id: string } | null>(null);
  function latest(value: MessagePage) {
    const ids = new Set(messageCache.current.map(message => message.id));
    const gap = ids.size > 0 && value.items.length > 0 && !value.items.some(message => ids.has(message.id));
    if (gap) {
      generation.current += 1;
      messageCache.current = value.items;
      setOlder(value.next_before); olderRef.current = value.next_before;
      setHistoryNotice("Newer replies arrived. Load older replies again to see the complete history.");
    } else messageCache.current = mergeMessages(messageCache.current, value.items);
    setMessages(messageCache.current);
  }
  useEffect(() => () => {
    for (const url of previews.current) URL.revokeObjectURL(url);
    previews.current.clear();
  }, []);
  useEffect(() => {
    let active = true;
    generation.current += 1;
    let initialized = false;
    messageCache.current = []; setMessages([]); setOlder(null); olderRef.current = null;
    const refresh = () => api<MessagePage>(endpoint + "?paged=true").then(value => {
      if (!active) return;
      latest(value); setReadError("");
      if (!initialized) { setOlder(value.next_before); olderRef.current = value.next_before; initialized = true; }
      if (document.visibilityState === "visible" && document.hasFocus()) {
        api<{ changed: boolean }>(`/auth/notifications/${token ? "customer" : "company"}/read-report`, "POST", { report: token || feedbackId })
          .then(result => { if (result.changed) window.dispatchEvent(new Event("bugbrief-notifications-updated")); }).catch(() => {});
      }
    }).catch(e => { if (active) { setReadError(e.message); if ([401, 403, 404].includes(e.status)) {
      generation.current += 1; initialized = false; messageCache.current = []; setMessages([]); setOlder(null); olderRef.current = null;
    } } });
    void refresh();
    const timer = window.setInterval(refresh, 15000);
    window.addEventListener("focus", refresh);
    window.addEventListener("bugbrief-reports-updated", refresh);
    return () => {
      active = false; clearInterval(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("bugbrief-reports-updated", refresh);
    };
  }, [endpoint]);
  function discard(image: PendingImage) {
    URL.revokeObjectURL(image.preview); previews.current.delete(image.preview);
    setImages(previous => previous.filter(value => value.key !== image.key));
  }
  return <section className="conversation-card" aria-label="Report conversation">
    <span className="eyebrow">KEEP THE DETAILS TOGETHER</span><h3>Conversation</h3>
    <p>{token ? "Reply to the team here. Your replies stay with this report." : "Reply to the customer or leave a private note for your team."}</p>
    {older && <button type="button" className="secondary-button" disabled={loadingOlder || !!readError} onClick={async () => {
      const epoch = generation.current; const cursor = olderRef.current;
      if (!cursor) return;
      setLoadingOlder(true);
      try {
        const value = await api<MessagePage>(endpoint + `?paged=true&before=${encodeURIComponent(cursor)}`);
        if (epoch !== generation.current) return;
        messageCache.current = mergeMessages(messageCache.current, value.items); setMessages(messageCache.current);
        setOlder(value.next_before); olderRef.current = value.next_before;
      } catch (e) { setReadError((e as Error).message); } finally { setLoadingOlder(false); }
    }}>{loadingOlder ? "Loading earlier replies…" : "Load older replies"}</button>}
    <div className="message-list" aria-live="polite">
      {!messages.length && <p className="empty-conversation">No replies yet. Start the conversation below.</p>}
      {messages.map(message => <article key={message.id} className={`report-message ${message.visibility === "internal" ? "internal-message" : ""}`}>
        <div><strong>{message.author_name}</strong><span>{message.visibility === "internal" ? "Private · team only" : message.author_role === "company" ? "Company reply" : "Customer reply"}</span></div>
        <p>{message.body}</p>
        {!!message.attachments?.length && <div className="reply-images">{message.attachments.map(image => {
          const url = `/api${endpoint}/${message.id}/attachments/${image.id}/content`;
          return <figure key={image.id}>
            <a href={url} target="_blank" rel="noreferrer" aria-label={`Open reply screenshot ${image.filename}`}>
              <img src={url} alt={image.caption || `Reply screenshot: ${image.filename}`} loading="lazy" />
            </a>
            <figcaption>{image.caption && <strong>{image.caption}</strong>}<span>{image.filename} · {image.width} × {image.height}</span></figcaption>
          </figure>;
        })}</div>}
        <time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString()}</time>
      </article>)}
    </div>
    <small>{messages.length} message{messages.length === 1 ? "" : "s"} loaded{older ? " · Earlier replies available" : ""}.</small>
    {historyNotice && <p role="status">{historyNotice}</p>}
    {readError && <div className="alert error" role="alert">{readError}</div>}
    {readOnly ? <p className="permission-notice">You have view-only access. Ask the workspace owner for Contributor access to reply.</p> : <form onSubmit={async event => {
      event.preventDefault();
      if (reviewOpen) return;
      setBusy(true); setSendError("");
      const attachments = images.map(({ filename, caption, mime_type, content_base64, reviewed }) => ({ filename, caption, mime_type, content_base64, reviewed }));
      const signature = JSON.stringify({ body, visibility, attachments });
      if (pending.current?.signature !== signature) pending.current = { signature, id: crypto.randomUUID() };
      try {
        const sent = await api<Message[]>(endpoint, "POST", { body, visibility, attachments, request_id: pending.current.id });
        latest({ items: sent, next_before: sent.length === 100 ? sent[0].id : null });
        pending.current = null;
        setBody("");
        for (const image of images) { URL.revokeObjectURL(image.preview); previews.current.delete(image.preview); }
        setImages([]);
        window.dispatchEvent(new Event("bugbrief-reports-updated"));
      } catch (e) {
        if (e instanceof ApiError && e.status < 500) pending.current = null;
        setSendError((e as Error).message);
      } finally { setBusy(false); }
    }}>
      {!token && <label>Message visibility
        <select aria-label="Message visibility" value={visibility} disabled={busy} onChange={event => setVisibility(event.target.value)}>
          <option value="public">Reply to customer</option><option value="internal">Private team note</option>
        </select>
      </label>}
      <label>{visibility === "internal" ? "Private team note" : "Your reply"}
        <textarea aria-label={visibility === "internal" ? "Private team note" : "Your reply"} required maxLength={4000} rows={3} value={body} disabled={busy} onChange={event => setBody(event.target.value)} />
      </label>
      <small>{visibility === "internal" ? "Only company employees and the workspace owner can see this note and its screenshots." : "This reply and its screenshots are visible to the customer and the company."}</small>
      <div className="pending-reply-images">{images.map((image, index) => <div className="pending-reply-image" key={image.key}>
        <img src={image.preview} alt={`Reviewed reply screenshot ${index + 1}`} />
        <label>Screenshot caption {index + 1}<input aria-label={`Screenshot caption ${index + 1}`} maxLength={500} value={image.caption} disabled={busy} onChange={event => setImages(previous => previous.map(value => value.key === image.key ? { ...value, caption: event.target.value } : value))} placeholder="What should the team look at?" /></label>
        <button type="button" className="icon-button" disabled={busy} aria-label={`Remove reply screenshot ${index + 1}`} onClick={() => discard(image)}><X size={17} /></button>
      </div>)}</div>
      {!reviewOpen && images.length < 3 && <button type="button" className="secondary-button" disabled={busy} onClick={() => { setReviewOpen(true); setSendError(""); }}><ImagePlus size={16} />{images.length ? "Add another screenshot" : "Add screenshots to reply"}</button>}
      {reviewOpen && <div className="reply-screenshot-review">
        <ScreenshotReview mode="reply" busy={busy} onError={setSendError} onSave={async (blob, filename) => {
          const content = await base64(blob);
          const preview = URL.createObjectURL(blob); previews.current.add(preview);
          setImages(previous => [...previous, { key: crypto.randomUUID(), filename, caption: "", mime_type: blob.type, content_base64: content, reviewed: true, preview }]);
          setReviewOpen(false); setSendError("");
        }} />
        <button type="button" className="text-button" disabled={busy} onClick={() => { setReviewOpen(false); setSendError(""); }}>Cancel screenshot</button>
        <small>Attach the reviewed screenshot or cancel its preview before sending your reply.</small>
      </div>}
      <small>Up to 3 PNG/JPEG screenshots per reply, 2 MiB each. Add a caption if useful. Unsent images stay in this tab and are lost on reload. Screenshots are not analyzed automatically.</small>
      {sendError && <div className="alert error" role="alert">{sendError}</div>}
      <button className="primary-button" disabled={busy || reviewOpen || !body.trim()}>{busy ? "Saving…" : visibility === "internal" ? "Save private note" : "Send reply"}</button>
    </form>}
  </section>;
}
