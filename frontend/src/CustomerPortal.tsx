import NextStep, { nextStep } from "./NextStep";
import { activateCustomer, clearCustomerDrafts } from "./browserStorage";
import NotificationBell from "./NotificationBell";
import { useEffect, useState, useRef, type FormEvent } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Check,
  LoaderCircle,
  LogIn,
  MessageSquare,
  Plus,
  UserPlus,
} from "lucide-react";
import { api } from "./types";
import { VerificationBanner } from "./AccountSecurity";
import DeleteReportButton from "./DeleteReportButton";
import { WorkflowBadge } from "./WorkflowPanel";
import {
  savedSubmissions,
  forgetSubmission,
  type SavedSubmission,
} from "./customerStorage";

type Customer = {
  id: string;
  name: string;
  email: string;
  email_verified: boolean;
};
type Session = { authenticated: boolean; customer?: Customer };
type CustomerProject = {
  id: string;
  name: string;
  team_name: string;
  intake_token: string | null;
  closed: boolean;
};
function Header() {
  return (
    <header className="portal-header">
      <a className="welcome-brand" href="/">
        b<span>✳</span> bugbrief
      </a>
      <NotificationBell audience="customer" />
      <a className="portal-back" href="/">
        <ArrowLeft size={14} />
        Switch role
      </a>
    </header>
  );
}
function tokenFromLink(value: string, kind = "c") {
  const target = new URL(value.trim(), location.origin);
  const match = target.pathname.match(
    new RegExp(`^/(${kind})/([A-Za-z0-9_-]{43})/?$`),
  );
  if (target.origin !== location.origin || !match)
    throw new Error("Use the project invitation from this BugBrief site.");
  return match[2];
}
function returnPath() {
  const next = new URLSearchParams(location.search).get("next") || "";
  return /^\/(c|s)\/[A-Za-z0-9_-]{43}$/.test(next) ? next : "/customer";
}
function Reports({
  items,
  onChange,
  account = false,
}: {
  items: SavedSubmission[];
  onChange: () => Promise<void> | void;
  account?: boolean;
}) {
  return items.length ? (
    <div className="customer-report-list">
      {items.map((item) => (
        <article key={item.access_token}>
          <a href={`/s/${item.access_token}`}>
            <span className="role-icon">
              <MessageSquare size={20} />
            </span>
            <div>
              <strong>{item.summary || item.project_name}</strong>
              {item.summary && <span className="report-project-name">{item.project_name}</span>}
              <small>
                BB-{item.reference} ·{" "}
                {item.workflow ? (
                  <WorkflowBadge workflow={item.workflow} />
                ) : item.stage === "submitted" ? (
                  "Sent to the company"
                ) : (
                  "Draft"
                )}
                {item.workflow?.assigned_to && (
                  <span className="customer-assigned-name">
                    Assigned to {item.workflow.assigned_to.name}
                  </span>
                )}
              </small>
              <NextStep workflow={item.workflow} audience="customer" compact />
            </div>
            <ArrowRight size={17} />
          </a>
          <DeleteReportButton
            customer
            onDelete={async () => {
              const response = await fetch(
                `/api/public/submissions/${item.access_token}`,
                { method: "DELETE" },
              );
              if (!response.ok && response.status !== 404) {
                const data = await response.json();
                throw new Error(data.detail || "Could not delete your report.");
              }
              forgetSubmission(item.access_token);
              await onChange();
            }}
          />
        </article>
      ))}
    </div>
  ) : (
    <div className="customer-empty">
      <MessageSquare size={25} />
      <h3>Your reports will appear here.</h3>
      <p>
        {account
          ? "Choose a connected project to report a problem. Your reports will be available whenever you sign in."
          : "Reports from before you created an account stay available in this browser."}
      </p>
    </div>
  );
}
export default function CustomerPortal({
  mode = "home",
}: {
  mode?: "home" | "signup" | "signin";
}) {
  const [session, setSession] = useState<Session | null>(null);
  const accountIdentity = useRef<string | null>(null);
  const [items, setItems] = useState<SavedSubmission[]>([]);
  const [projects, setProjects] = useState<CustomerProject[]>([]);
  const [accountReady, setAccountReady] = useState(false);
  const [legacy, setLegacy] = useState(savedSubmissions);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [link, setLink] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  async function refresh() {
    const identity = await api<Session>("/customer/session");
    if (
      !identity.authenticated ||
      identity.customer?.id !== accountIdentity.current
    ) {
      activateCustomer(identity.customer?.id || "guest");
      location.reload();
      return;
    }
    const [reports, connected] = await Promise.all([
      api<SavedSubmission[]>("/customer/reports"),
      api<CustomerProject[]>("/customer/projects"),
    ]);
    setItems(reports);
    setProjects(connected);
    setAccountReady(true);
  }
  useEffect(() => {
    api<Session>("/customer/session")
      .then(async (value) => {
        accountIdentity.current = value.customer?.id || "guest";
        activateCustomer(accountIdentity.current);
        setLegacy(savedSubmissions());
        if (
          value.authenticated &&
          mode !== "home" &&
          returnPath() !== "/customer"
        ) {
          const next = returnPath();
          if (next.startsWith("/s/")) {
            const token = next.split("/")[2];
            await api("/customer/claims", "POST", { token });
            forgetSubmission(token, true);
          }
          location.replace(next);
          return;
        }
        setSession(value);
        if (value.authenticated) await refresh().catch(e => setError(e.message));
      })
      .catch((e) => {
        setSession({ authenticated: false });
        setError(e.message);
      });
  }, []);
  useEffect(() => {
    if (!session?.authenticated) return;
    const update = () => refresh().catch((e) => setError(e.message));
    const timer = setInterval(update, 15000);
    window.addEventListener("focus", update);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", update);
    };
  }, [session?.authenticated]);
  async function authenticate(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (mode === "signup" && password !== confirmPassword) {
      setError("Your passwords don’t match.");
      return;
    }
    setBusy(true);
    try {
      const loggedIn = await api<Session>(
        mode === "signup" ? "/customer/register" : "/customer/login",
        "POST",
        { email, password, ...(mode === "signup" ? { name } : {}) },
      );
      activateCustomer(loggedIn.customer!.id);
      const next = returnPath();
      if (next.startsWith("/s/")) {
        const token = next.split("/")[2];
        await api("/customer/claims", "POST", { token });
        forgetSubmission(token, true);
      }
      location.assign(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!session)
    return (
      <div className="access-loading">
        <LoaderCircle size={22} className="spin" />
        Opening customer portal…
      </div>
    );
  if (session.authenticated && !accountReady) return <div className="welcome-shell"><Header /><main className="customer-home">
    <h1>Opening your reports…</h1>
    {error ? <div className="alert error" role="alert">{error}<button className="secondary-button" onClick={() => { setError(""); void refresh().catch(e => setError(e.message)); }}>Try again</button></div> : <LoaderCircle className="spin" size={24} />}
  </main></div>;
  const activeProjects = projects.filter(project => !!project.intake_token);
  const attention = items.filter(item => item.stage !== "submitted" || ["needs_information", "ready_to_retest"].includes(item.workflow?.status || ""));
  const suffix =
    returnPath() !== "/customer"
      ? `?next=${encodeURIComponent(returnPath())}`
      : "";
  if (!session.authenticated && mode !== "home")
    return (
      <div className="welcome-shell">
        <Header />
        <main className="customer-auth">
          <a className="portal-back" href="/customer">
            <ArrowLeft size={14} />
            Customer portal
          </a>
          <span className="role-icon">
            {mode === "signup" ? <UserPlus size={26} /> : <LogIn size={26} />}
          </span>
          <span className="eyebrow">
            {mode === "signup" ? "NEW CUSTOMER" : "WELCOME BACK"}
          </span>
          <h1>
            {mode === "signup"
              ? "A place for your reports."
              : "Sign in to your reports."}
          </h1>
          <p>
            {mode === "signup"
              ? "Create your account to keep your projects and reports together."
              : "Pick up where you left off. No return link needed."}
          </p>
          <form onSubmit={authenticate}>
            {mode === "signup" && (
              <label>
                Your name
                <input
                  required
                  maxLength={80}
                  autoComplete="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
            )}
            <label>
              Email address
              <input
                required
                type="email"
                maxLength={254}
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label>
              Password
              <input
                required
                type="password"
                minLength={mode === "signup" ? 12 : undefined}
                maxLength={128}
                autoComplete={
                  mode === "signup" ? "new-password" : "current-password"
                }
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {mode === "signup" && (
              <>
                <small>
                  Use at least 12 characters. A memorable phrase works well.
                </small>
                <label>
                  Confirm password
                  <input
                    required
                    type="password"
                    maxLength={128}
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                  />
                </label>
              </>
            )}
            {returnPath().startsWith("/s/") && (
              <div className="customer-notice">
                This report will be added to your account.
              </div>
            )}
            {error && (
              <div className="alert error" role="alert">
                {error}
              </div>
            )}
            <button className="primary-button full-width" disabled={busy}>
              {busy ? (
                <LoaderCircle size={16} className="spin" />
              ) : (
                <ArrowRight size={16} />
              )}
              {mode === "signup" ? "Create customer account" : "Sign in"}
            </button>
          </form>
          {mode === "signin" && (
            <p className="auth-alternative">
              <a href="/account?role=customer">Forgot password?</a>
            </p>
          )}
          <p className="auth-alternative">
            {mode === "signup" ? "Already have an account?" : "New here?"}{" "}
            <a
              href={`/customer/${mode === "signup" ? "signin" : "signup"}${suffix}`}
            >
              {mode === "signup" ? "Sign in" : "Create an account"}
            </a>
          </p>
        </main>
      </div>
    );
  if (!session.authenticated)
    return (
      <div className="welcome-shell">
        <Header />
        <main className="customer-home">
          <span className="eyebrow">CUSTOMER PORTAL</span>
          <h1>Let’s get it to the right team.</h1>
          <p>
            New here or coming back? Your account keeps your reports in one
            place.
          </p>
          <div className="role-options customer-entry-options">
            <a className="role-option" href="/customer/signup">
              <span className="role-icon">
                <UserPlus size={26} />
              </span>
              <span className="eyebrow">FIRST TIME HERE?</span>
              <h2>I’m a new customer</h2>
              <p>
                Create an account, connect your project and tell the team what
                went wrong.
              </p>
              <span className="role-cta">
                Create an account <ArrowRight size={17} />
              </span>
            </a>
            <a className="role-option customer-option" href="/customer/signin">
              <span className="role-icon">
                <LogIn size={26} />
              </span>
              <span className="eyebrow">ALREADY A CUSTOMER?</span>
              <h2>I’m a returning customer</h2>
              <p>
                Sign in to view your reports, add a new issue or manage an
                existing submission.
              </p>
              <span className="role-cta">
                Sign in <ArrowRight size={17} />
              </span>
            </a>
          </div>
          {error && (
            <div className="alert error" role="alert">
              {error}
            </div>
          )}
          {legacy.length > 0 && (
            <section className="my-reports">
              <div className="section-heading">
                <div>
                  <h2>Previous reports in this browser</h2>
                  <p>
                    Open a previous report and save it to your account to find
                    it after signing in.
                  </p>
                </div>
              </div>
              <Reports
                items={legacy}
                onChange={() => setLegacy(savedSubmissions())}
              />
            </section>
          )}
        </main>
      </div>
    );
  return (
    <div className="welcome-shell">
      <Header />
      <main className="customer-home customer-signed-in">
        <div className="customer-account-heading">
          <div>
            <span className="eyebrow">YOUR CUSTOMER ACCOUNT</span>
            <h1>Hello, {session.customer!.name}.</h1>
            <p>{session.customer!.email}</p>
            <VerificationBanner
              scope="customer"
              verified={session.customer!.email_verified}
            />
          </div>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                await api("/customer/logout", "POST");
                clearCustomerDrafts();
                location.assign("/customer");
              } catch (e) {
                setError((e as Error).message);
                setBusy(false);
              }
            }}
          >
            Sign out
          </button>
        </div>
        {error && (
          <div className="alert error" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="customer-notice" role="status">
            <Check size={15} />
            {notice}
          </div>
        )}
        <section className="customer-start" aria-label="Your next step">
          <div>
            <span className="eyebrow">YOUR NEXT STEP</span>
            <h2>{!projects.length ? "Connect your project to get started." : activeProjects.length ? "Report an issue or pick up a conversation." : "Your projects are closed for new reports."}</h2>
            <p>{!projects.length ? "Use the invitation from the company that manages your website. They’ll receive the issues you send." : activeProjects.length ? "Your reports and replies stay together. Only you and the project team can access your reports." : "You can still open existing reports and reply to the team. Contact them if you need to report a new issue."}</p>
          </div>
          {activeProjects.length === 1 ?
            <a className="primary-button" href={`/c/${activeProjects[0].intake_token}`}><Plus size={16} />Report an issue</a> :
            <a className="primary-button" href={!projects.length ? "#project-invitation" : activeProjects.length ? "#your-projects" : "#your-reports"}>{!projects.length ? "Connect your project" : activeProjects.length ? "Choose a project" : "View your reports"}<ArrowRight size={16} /></a>}
        </section>
        {attention.length > 0 && <section className="customer-attention" aria-label="Reports needing your action">
          <h2>Needs your attention <span className="count-badge">{attention.length}</span></h2>
          <div>{attention.map(item => <a key={item.access_token} href={`/s/${item.access_token}`}>
            <strong>{nextStep(item.workflow, "customer").title}</strong>
            <span>{item.summary || item.project_name} · BB-{item.reference}</span><ArrowRight size={16} />
          </a>)}</div>
        </section>}
        <section className="my-reports">
          <div className="section-heading">
            <div>
              <h2>
                <span id="your-reports">Your reports</span> <span className="count-badge">{items.length}</span>
              </h2>
              <p>Available across browsers whenever you sign in.</p>
            </div>
          </div>
          <Reports account items={items} onChange={refresh} />
        </section>
        <section className="my-reports">
          <div className="section-heading">
            <div>
              <h2 id="your-projects">Your projects</h2>
              <p>Choose the website or app with the issue. The named team receives your report.</p>
            </div>
          </div>
          {projects.length > 0 && (
            <div className="customer-project-grid">
              {projects.map((project) => (
                <article key={project.id}>
                  <Building2 size={24} />
                  <h3>{project.name}</h3>
                  <p className="project-team-name">Managed by {project.team_name || "your project team"}</p>
                  {project.intake_token ? (
                    <a
                      className="primary-button"
                      href={`/c/${project.intake_token}`}
                    >
                      <Plus size={15} />
                      Report an issue
                    </a>
                  ) : (
                    <small>This project is closed for new reports.</small>
                  )}
                </article>
              ))}
            </div>
          )}
          <details className="connect-project" open={projects.length === 0}>
            <summary>
              {projects.length
                ? "Connect another project"
                : "Connect your first project"}
            </summary>
            <p>
              Use the project invitation your company shared once. Then choose
              this project here whenever you sign in.
            </p>
            <form
              onSubmit={async (event) => {
                event.preventDefault();
                setBusy(true);
                setError("");
                setNotice("");
                try {
                  const token = tokenFromLink(link);
                  await api("/customer/projects", "POST", { token });
                  setLink("");
                  await refresh();
                  setNotice("Project connected. You can now report a problem.");
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label htmlFor="project-invitation">Project invitation</label>
              <div>
                <input
                  id="project-invitation"
                  required
                  value={link}
                  onChange={(e) => setLink(e.target.value)}
                  placeholder="Paste the project invitation"
                />
                <button className="primary-button" disabled={busy}>
                  Connect project <ArrowRight size={15} />
                </button>
              </div>
            </form>
            <small>
              Don’t have an invitation? Ask the company that manages the
              website.
            </small>
          </details>
        </section>
        {legacy.filter(
          (item) =>
            !items.some((saved) => saved.access_token === item.access_token),
        ).length > 0 && (
          <section className="my-reports">
            <div className="section-heading">
              <div>
                <h2>Bring your previous reports</h2>
                <p>Choose reports from this browser to save to your account.</p>
              </div>
            </div>
            <div className="legacy-claims">
              {legacy
                .filter(
                  (item) =>
                    !items.some(
                      (saved) => saved.access_token === item.access_token,
                    ),
                )
                .map((item) => (
                  <article key={item.access_token}>
                    <div>
                      <strong>{item.project_name}</strong>
                      <small>BB-{item.reference}</small>
                    </div>
                    <button
                      className="secondary-button"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true);
                        setError("");
                        try {
                          await api("/customer/claims", "POST", {
                            token: item.access_token,
                          });
                          forgetSubmission(item.access_token, true);
                          setLegacy(savedSubmissions());
                          await refresh();
                        } catch (e) {
                          setError((e as Error).message);
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      Save to my account
                    </button>
                  </article>
                ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
