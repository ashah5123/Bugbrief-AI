import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ArrowRight, KeyRound, LoaderCircle, ShieldCheck } from "lucide-react";
export default function AgencyGate({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    fetch("/api/auth/session")
      .then((r) => r.json())
      .then((data) => setAuthenticated(data.authenticated))
      .catch(() => {
        setAuthenticated(false);
        setError(
          "Cannot reach the workspace. Check that the backend is running.",
        );
      });
  }, []);
  async function login(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not sign in.");
      setCode("");
      setAuthenticated(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (authenticated === true) return children;
  if (authenticated === null)
    return (
      <div className="access-loading">
        <LoaderCircle size={22} className="spin" />
        Opening your workspace…
      </div>
    );
  return (
    <div className="agency-access">
      <div className="access-brand">
        b<span>✳</span> bugbrief
      </div>
      <section className="access-card">
        <a className="portal-back" href="/">
          ← Switch role
        </a>
        <span className="access-lock">
          <KeyRound size={25} />
        </span>
        <span className="eyebrow">FOR YOUR AGENCY</span>
        <h1>Your workspace. Your clients.</h1>
        <p>
          Sign in to review customer submissions, share project links, and turn
          collected evidence into a clear handoff.
        </p>
        <form onSubmit={login}>
          <label>
            Workspace access code
            <input
              type="password"
              autoComplete="current-password"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              autoFocus
            />
          </label>
          {error && (
            <div className="alert error" role="alert">
              {error}
            </div>
          )}
          <button
            className="primary-button full-width"
            disabled={busy || !code}
          >
            {busy ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <ArrowRight size={16} />
            )}
            Open workspace
          </button>
        </form>
        <div className="access-help">
          <ShieldCheck size={17} />
          <p>
            Local setup: your access code is in{" "}
            <code>data/agency-access.txt</code> on this Mac. Customers use their
            project link and don’t need this code.
          </p>
        </div>
      </section>
      <span className="access-footnote">
        A little clarity. A better handoff.
      </span>
    </div>
  );
}
