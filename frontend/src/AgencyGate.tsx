import {
  createContext,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  KeyRound,
  LoaderCircle,
  LogIn,
  UserPlus,
} from "lucide-react";
import { api } from "./types";

export type Employee = { id: string; name: string; email: string };
export const EmployeeContext = createContext<Employee | null>(null);
export default function AgencyGate({
  children,
  mode = "home",
}: {
  children: ReactNode;
  mode?: "home" | "signup" | "signin";
}) {
  const forceChoice =
    new URLSearchParams(location.search).get("employee") === "choose";
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ authenticated: boolean; employee?: Employee }>("/auth/session")
      .then((data) => {
        setAuthenticated(data.authenticated);
        setEmployee(data.employee || null);
      })
      .catch(() => {
        setAuthenticated(false);
        setError(
          "Cannot reach the workspace. Check that the backend is running.",
        );
      });
  }, []);
  async function authenticate(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (mode === "signup" && password !== confirmation) {
      setError("Your passwords don’t match.");
      return;
    }
    setBusy(true);
    try {
      await api(
        `/auth/employee/${mode === "signup" ? "register" : "login"}`,
        "POST",
        {
          email,
          password,
          ...(mode === "signup" ? { name, workspace_code: code } : {}),
        },
      );
      location.assign("/workspace");
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  async function ownerLogin(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/login", "POST", { code });
      location.assign("/workspace");
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  if (authenticated === true && mode === "home" && !forceChoice)
    return (
      <EmployeeContext.Provider value={employee}>
        {children}
      </EmployeeContext.Provider>
    );
  if (authenticated === null)
    return (
      <div className="access-loading">
        <LoaderCircle size={22} className="spin" />
        Opening your workspace…
      </div>
    );
  return (
    <div className="welcome-shell">
      <header className="portal-header">
        <a className="welcome-brand" href="/">
          b<span>✳</span> bugbrief
        </a>
        <a className="portal-back" href="/">
          <ArrowLeft size={14} />
          Switch role
        </a>
      </header>
      {mode === "home" ? (
        <main className="customer-home employee-home">
          <span className="eyebrow">COMPANY WORKSPACE</span>
          <h1>Your workspace. Your clients.</h1>
          <p>
            Joining the team or picking up where you left off? Choose your next
            step.
          </p>
          {authenticated && (
            <a className="primary-button employee-continue" href="/workspace">
              {employee
                ? `Continue as ${employee.name}`
                : "Continue to workspace"}
              <ArrowRight size={16} />
            </a>
          )}
          <div className="role-options">
            <a className="role-option" href="/workspace/signup">
              <span className="role-icon">
                <UserPlus size={27} />
              </span>
              <span className="eyebrow">JOIN THE TEAM</span>
              <h2>I’m a new employee</h2>
              <p>
                Create your employee account with an invitation from your
                workspace owner.
              </p>
              <span className="role-cta">
                Join the workspace <ArrowRight size={17} />
              </span>
            </a>
            <a className="role-option customer-option" href="/workspace/signin">
              <span className="role-icon">
                <LogIn size={27} />
              </span>
              <span className="eyebrow">WELCOME BACK</span>
              <h2>I’m an existing employee</h2>
              <p>
                Sign in to review customer feedback, manage projects and keep
                reports moving.
              </p>
              <span className="role-cta">
                Employee sign in <ArrowRight size={17} />
              </span>
            </a>
          </div>
          <div className="employee-team-note">
            <Building2 size={17} />
            <p>
              Employee accounts share this company’s workspace. Customer
              accounts have their own portal.
            </p>
          </div>
          <details className="owner-access">
            <summary>
              <KeyRound size={14} />
              Workspace owner access
            </summary>
            <p>
              For initial setup, or if you already use the workspace access
              code.
            </p>
            <form onSubmit={ownerLogin}>
              <label htmlFor="owner-code">Workspace access code</label>
              <div>
                <input
                  id="owner-code"
                  type="password"
                  required
                  maxLength={256}
                  autoComplete="off"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
                <button className="primary-button" disabled={busy || !code}>
                  {busy ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <ArrowRight size={16} />
                  )}
                  Open workspace
                </button>
              </div>
            </form>
            <small>
              Local setup: the workspace owner’s code is in{" "}
              <code>data/agency-access.txt</code>. Share it only with employees
              you want to invite.
            </small>
          </details>
          {error && (
            <div className="alert error" role="alert">
              {error}
            </div>
          )}
        </main>
      ) : (
        <main className="customer-auth employee-auth">
          <a className="portal-back" href="/workspace">
            <ArrowLeft size={14} />
            Company workspace
          </a>
          <span className="role-icon">
            {mode === "signup" ? <UserPlus size={26} /> : <LogIn size={26} />}
          </span>
          <span className="eyebrow">
            {mode === "signup" ? "NEW EMPLOYEE" : "EXISTING EMPLOYEE"}
          </span>
          <h1>
            {mode === "signup"
              ? "Your place on the team."
              : "Welcome back to work."}
          </h1>
          <p>
            {mode === "signup"
              ? "Use your workspace invitation to create your own employee login."
              : "Sign in with your employee email and password to open the company workspace."}
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
              Work email
              <input
                required
                type="email"
                maxLength={254}
                autoComplete="username"
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
                    value={confirmation}
                    onChange={(e) => setConfirmation(e.target.value)}
                  />
                </label>
                <label>
                  Workspace invitation code
                  <input
                    required
                    type="password"
                    maxLength={256}
                    autoComplete="off"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                  />
                </label>
                <small>
                  Ask your workspace owner for this code. Customer project
                  invitations won’t grant employee access.
                </small>
              </>
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
              {mode === "signup"
                ? "Create employee account"
                : "Sign in to workspace"}
            </button>
          </form>
          <p className="auth-alternative">
            {mode === "signup"
              ? "Already joined the team?"
              : "New to the team?"}{" "}
            <a href={`/workspace/${mode === "signup" ? "signin" : "signup"}`}>
              {mode === "signup"
                ? "Employee sign in"
                : "Create an employee account"}
            </a>
          </p>
        </main>
      )}
    </div>
  );
}
