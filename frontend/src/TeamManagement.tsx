import ProjectAccess from "./ProjectAccess";
import ReminderSettings from "./ReminderSettings";
import NotificationBell from "./NotificationBell";
import { useEffect, useState } from "react";
import { api } from "./types";
import { VerificationBanner } from "./AccountSecurity";
import { useContext } from "react";
import { EmployeeContext } from "./AgencyGate";
type Team = {
  can_manage: boolean;
  mail_mode: string | null;
  employees: {
    id: string;
    name: string;
    email: string;
    disabled_at: string | null;
    email_verified: boolean;
  }[];
  invitations: { id: string; email: string; expires_at: number }[];
};
type Mail = {
  id: string;
  recipient: string;
  subject: string;
  body: string;
  delivery: string;
  created_at: string;
};
export default function TeamManagement() {
  const employee = useContext(EmployeeContext);
  const [team, setTeam] = useState<Team | null>(null);
  const [mail, setMail] = useState<Mail[]>([]);
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  async function refresh() {
    const value = await api<Team>("/team");
    setTeam(value);
    if (value.can_manage) setMail(await api<Mail[]>("/team/outbox"));
  }
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
  }, []);
  async function act(path: string, method: string, data?: unknown) {
    setBusy(true);
    setError("");
    try {
      await api(path, method, data);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="welcome-shell">
      <header className="portal-header">
        <a className="welcome-brand" href="/">
          b<span>✳</span> bugbrief
        </a>
        <NotificationBell audience="company" />
        <a href="/workspace">← Back to workspace</a>
      </header>
      <main className="customer-home team-page">
        <span className="eyebrow">PEOPLE & ACCOUNT ACCESS</span>
        <h1>Your team.</h1>
        <p>Invite employees, manage access and test account emails.</p>
        {employee && (
          <VerificationBanner
            scope="employee"
            verified={employee.email_verified}
          />
        )}
        {error && (
          <div className="alert error" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <p className="customer-notice" role="status">
            {notice}
          </p>
        )}
        {!team && !error && <p>Loading team…</p>}
        {team && !team.can_manage && (
          <section className="conversation-card">
            <h2>Team access is managed by your workspace owner</h2>
            <p>
              Your employee login gives you access to the projects assigned to
              you and their reports. Ask the owner to invite a colleague or
              change employee access.
            </p>
            <a href="/workspace?employee=choose">
              Open workspace owner sign in →
            </a>
          </section>
        )}
        {team?.can_manage && (
          <>
            <section className="conversation-card">
              <h2>Invite an employee</h2>
              <p>
                Each invitation is bound to one email address, expires in seven
                days and can be used once.
              </p>
              <form
                onSubmit={async (event) => {
                  event.preventDefault();
                  setBusy(true);
                  setError("");
                  try {
                    const result = await api<{ delivery: string }>(
                      "/team/invitations",
                      "POST",
                      { email },
                    );
                    setNotice(
                      result.delivery === "local"
                        ? "Invitation prepared. Open the test email below."
                        : result.delivery === "sent"
                          ? "Invitation sent."
                          : "Email delivery failed. Check your sender settings and issue a new invitation.",
                    );
                    setEmail("");
                    await refresh();
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <label>
                  Employee email
                  <input
                    type="email"
                    required
                    maxLength={254}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>
                <button className="primary-button" disabled={busy}>
                  Create invitation
                </button>
              </form>
            </section>
            <section className="conversation-card">
              <h2>Employees</h2>
              {!team.employees.length && <p>No employee accounts yet.</p>}
              {team.employees.map((member) => (
                <article className="team-member" key={member.id}>
                  <div>
                    <strong>{member.name}</strong>
                    <p>{member.email}</p>
                    <small>
                      {member.disabled_at
                        ? "Access removed"
                        : member.email_verified
                          ? "Active · email verified"
                          : "Active · email not verified"}
                    </small>
                  </div>
                  <button
                    className="secondary-button"
                    disabled={busy}
                    onClick={() => {
                      if (member.disabled_at)
                        void act(
                          `/team/employees/${member.id}/restore`,
                          "POST",
                        );
                      else if (
                        window.confirm(
                          `Remove ${member.name}’s workspace access? They will be signed out and their reports will become unassigned.`,
                        )
                      )
                        void act(`/team/employees/${member.id}`, "DELETE");
                    }}
                  >
                    {member.disabled_at ? "Restore access" : "Remove access"}
                  </button>
                </article>
              ))}
            </section>
            <ProjectAccess />
            <ReminderSettings />
            <section className="conversation-card">
              <h2>Pending invitations</h2>
              {!team.invitations.length && <p>No pending invitations.</p>}
              {team.invitations.map((invitation) => (
                <article className="team-member" key={invitation.id}>
                  <div>
                    <strong>{invitation.email}</strong>
                    <p>
                      Expires{" "}
                      {new Date(invitation.expires_at * 1000).toLocaleString()}
                    </p>
                  </div>
                  <button
                    disabled={busy}
                    className="secondary-button"
                    onClick={() =>
                      void act(`/team/invitations/${invitation.id}`, "DELETE")
                    }
                  >
                    Revoke invitation
                  </button>
                </article>
              ))}
            </section>
            <section className="conversation-card">
              <div className="progress-card-heading">
                <h2>
                  {team.mail_mode === "local"
                    ? "Test email outbox"
                    : "Email delivery"}
                </h2>
                <button
                  className="secondary-button"
                  disabled={busy}
                  onClick={() =>
                    void refresh().catch((e) => setError(e.message))
                  }
                >
                  Refresh outbox
                </button>
              </div>
              <p>
                {team.mail_mode === "local"
                  ? "Local testing mode: no emails are sent. Only the workspace owner can view these messages. Use the link for the intended account."
                  : "Delivery status for recent account emails."}
              </p>
              {!mail.length && <p>No account emails yet.</p>}
              {mail.map((item) => (
                <details className="outbox-message" key={item.id}>
                  <summary>
                    <strong>{item.subject}</strong>
                    <span>
                      {item.recipient} · {item.delivery}
                    </span>
                  </summary>
                  <time>{new Date(item.created_at).toLocaleString()}</time>
                  {item.body && (
                    <>
                      <pre>{item.body}</pre>
                      {item.body.match(/https?:\/\/\S+/) && (
                        <a
                          className="secondary-button"
                          href={item.body.match(/https?:\/\/\S+/)![0]}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Open account link ↗
                        </a>
                      )}
                    </>
                  )}
                </details>
              ))}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
