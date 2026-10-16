import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  Check,
  Code2,
  Copy,
  Globe,
  Link2,
  LoaderCircle,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, type Project } from "./types";
export default function ShareProject({
  projects,
  initialId,
  close,
}: {
  projects: Project[];
  initialId?: string;
  close: () => void;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const [id, setId] = useState(initialId || projects[0]?.id || "");
  const [token, setToken] = useState("");
  const [website, setWebsite] = useState(
    projects.find((p) => p.id === initialId)?.url || projects[0]?.url || "",
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState("");
  useEffect(() => {
    let cancelled = false;
    setToken("");
    setWebsite(projects.find((p) => p.id === id)?.url || "");
    setError("");
    if (!id) return;
    setBusy(true);
    api<{ token: string }>(`/projects/${id}/intake-link`, "POST", {})
      .then((data) => {
        if (!cancelled) setToken(data.token);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.querySelector("select")?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key === "Tab") {
        const controls = Array.from(
          dialogRef.current?.querySelectorAll<HTMLElement>(
            "button:not(:disabled),input,select,textarea,a[href],summary",
          ) || [],
        ).filter((control) => control.getClientRects().length > 0);
        if (!controls.length) return;
        const first = controls[0],
          last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, [close]);
  const url = `${location.origin}/c/${token}`;
  const embed = `<script src="${location.origin}/widget.js" data-project="${token}" defer></script>`;
  const local = ["127.0.0.1", "localhost"].includes(location.hostname);
  async function copy(text: string, kind: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(kind);
    } catch {
      setError("Select and copy the text from the field below.");
    }
  }
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <section
        ref={dialogRef}
        className="modal share-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Collect customer feedback"
      >
        <button
          className="icon-button modal-close"
          aria-label="Close sharing dialog"
          onClick={close}
        >
          <X size={20} />
        </button>
        <span className="eyebrow">COLLECT THE DETAILS AT THE SOURCE</span>
        <h2>Let your customers show you.</h2>
        <p className="muted">
          One link or one button. Their feedback, screenshots and answers arrive
          together in your review inbox.
        </p>
        <label className="share-project-select">
          Project
          <select
            aria-label="Project"
            autoFocus
            value={id}
            onChange={(event) => setId(event.target.value)}
          >
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
        {error && (
          <div className="alert error" role="alert">
            {error}
          </div>
        )}
        {busy && (
          <div className="loading-line">
            <LoaderCircle size={15} className="spin" />
            Preparing the project link…
          </div>
        )}
        {token && (
          <>
            <div className="share-option">
              <span className="share-option-icon">
                <Link2 size={19} />
              </span>
              <div>
                <h3>Send a feedback link</h3>
                <p>Works without installing anything on the customer’s site.</p>
              </div>
            </div>
            <div className="share-copy">
              <input aria-label="Customer feedback link" value={url} readOnly />
              <button
                className="secondary-button"
                onClick={() => copy(url, "link")}
              >
                {copied === "link" ? <Check size={14} /> : <Copy size={14} />}
                Copy link
              </button>
            </div>
            <a
              className="text-button share-open"
              href={url}
              target="_blank"
              rel="noreferrer"
            >
              Open customer form <ArrowUpRight size={13} />
            </a>
            <div className="share-option">
              <span className="share-option-icon">
                <Code2 size={19} />
              </span>
              <div>
                <h3>Add “Report a problem” to their site</h3>
                <p>
                  Captures that page’s URL and viewport when the form opens. No
                  query strings, cookies or browsing history.
                </p>
              </div>
            </div>
            <div className="share-website">
              <label>
                Website URL for embedded capture
                <input
                  type="url"
                  value={website}
                  onChange={(event) => setWebsite(event.target.value)}
                  placeholder="https://customer-site.com"
                />
              </label>
              <button
                className="secondary-button"
                onClick={async () => {
                  const project = projects.find((p) => p.id === id);
                  if (!project) return;
                  try {
                    await api(`/projects/${id}`, "PUT", {
                      name: project.name,
                      url: website.trim(),
                    });
                    setCopied("website");
                    setError("");
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                {copied === "website" ? (
                  <Check size={13} />
                ) : (
                  <Globe size={13} />
                )}
                {copied === "website"
                  ? "Website URL saved"
                  : "Save website URL"}
              </button>
            </div>
            <textarea
              className="embed-code"
              aria-label="Embed code"
              readOnly
              value={embed}
              rows={3}
            />
            <div className="share-embed-actions">
              <button
                className="secondary-button"
                onClick={() => copy(embed, "embed")}
              >
                {copied === "embed" ? <Check size={14} /> : <Copy size={14} />}
                Copy embed code
              </button>
              <a
                className="text-button"
                target="_blank"
                rel="noreferrer"
                href={`/demo/${token}`}
              >
                Try the embedded demo <ArrowUpRight size={13} />
              </a>
            </div>
            <p className="fine-print">
              Set the project URL to the customer site’s origin to accept its
              captured page context. Add the snippet before the site’s closing
              body tag.
            </p>
            {local && (
              <div className="share-local-note">
                <ShieldCheck size={17} />
                <p>
                  <strong>This link is for local testing.</strong> It works on
                  this Mac. Remote customers need a reachable HTTPS deployment;
                  nothing has been published online.
                </p>
              </div>
            )}
            <details className="share-revoke">
              <summary>Close this project link</summary>
              <p>
                Revoking closes the current intake link and its private return
                links. Existing agency reports stay saved.
              </p>
              <button
                className="secondary-button"
                onClick={async () => {
                  try {
                    await api(`/projects/${id}/intake-link`, "DELETE");
                    setToken("");
                    setError(
                      "Link closed. Reopen this dialog to create a new link.",
                    );
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                Revoke current link
              </button>
            </details>
          </>
        )}
      </section>
    </div>
  );
}
