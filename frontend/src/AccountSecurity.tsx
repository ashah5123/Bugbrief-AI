import { useEffect, useState } from "react";
import { api } from "./types";
export function VerificationBanner({
  scope,
  verified,
}: {
  scope: "employee" | "customer";
  verified: boolean;
}) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  if (verified) return <p className="verified-email">✓ Email verified</p>;
  return (
    <aside className="verification-banner">
      <div>
        <strong>Verify your email</strong>
        <p>
          Confirm your email address using the verification message sent when
          you joined.
        </p>
      </div>
      <button
        className="secondary-button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await api(`/auth/accounts/${scope}/verification`, "POST");
            setMessage(
              "Verification requested. For local testing, ask the workspace owner to open Team → Test email outbox.",
            );
          } catch (e) {
            setMessage((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Resend verification
      </button>
      {message && <p role="status">{message}</p>}
    </aside>
  );
}
export default function AccountSecurity() {
  useEffect(() => {
    const openSecurityLink = () => location.reload();
    window.addEventListener("hashchange", openSecurityLink);
    return () => window.removeEventListener("hashchange", openSecurityLink);
  }, []);
  const parts = location.hash.slice(1).split("/");
  const [scope] = useState(
    parts[0] === "employee" ||
      new URLSearchParams(location.search).get("role") === "employee"
      ? "employee"
      : "customer",
  );
  const [kind] = useState(parts[1] === "verify" ? "verify" : "reset");
  const [token] = useState(parts[2] || "");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const home = scope === "employee" ? "/workspace" : "/customer";
  return (
    <div className="welcome-shell">
      <header className="portal-header">
        <a className="welcome-brand" href="/">
          b<span>✳</span> bugbrief
        </a>
        <a href={home}>Back to account</a>
      </header>
      <main className="customer-auth">
        <span className="eyebrow">
          {scope === "employee" ? "EMPLOYEE ACCOUNT" : "CUSTOMER ACCOUNT"}
        </span>
        <h1>
          {token
            ? kind === "verify"
              ? "Confirm your email."
              : "Choose a new password."
            : "Forgot your password?"}
        </h1>
        <p>
          {token
            ? "This security link can only be used once."
            : "Enter your account email and we’ll prepare a password reset link."}
        </p>
        {!done && (
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              setError("");
              if (token && kind === "reset" && password !== confirmation) {
                setError("Your passwords don’t match.");
                return;
              }
              setBusy(true);
              try {
                const result = await api<{ message: string }>(
                  `/auth/accounts/${scope}/${token ? `${kind}/complete` : "recover"}`,
                  "POST",
                  token
                    ? { token, ...(kind === "reset" ? { password } : {}) }
                    : { email },
                );
                setMessage(result.message);
                setDone(true);
                history.replaceState(
                  null,
                  "",
                  location.pathname + location.search,
                );
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {!token && (
              <label>
                Account email
                <input
                  required
                  type="email"
                  autoComplete="email"
                  maxLength={254}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
            )}
            {token && kind === "reset" && (
              <>
                <label>
                  New password
                  <input
                    required
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>
                <label>
                  Confirm password
                  <input
                    required
                    type="password"
                    autoComplete="new-password"
                    maxLength={128}
                    value={confirmation}
                    onChange={(e) => setConfirmation(e.target.value)}
                  />
                </label>
                <small>Use at least 12 characters.</small>
              </>
            )}
            {error && (
              <div className="alert error" role="alert">
                {error}
              </div>
            )}
            <button className="primary-button" disabled={busy}>
              {busy
                ? "Please wait…"
                : !token
                  ? "Send reset link"
                  : kind === "verify"
                    ? "Verify email"
                    : "Update password"}
            </button>
          </form>
        )}
        {message && (
          <p className="customer-notice" role="status">
            {message}
          </p>
        )}
        {done && !token && (
          <p>
            For local testing, the workspace owner can open Team → Test email
            outbox to retrieve the message.
          </p>
        )}
        <p className="auth-alternative">
          <a href={home + "/signin"}>Return to sign in</a>
        </p>
      </main>
    </div>
  );
}
