import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  CheckCheck,
  ChevronLeft,
  Copy,
  Globe,
  Image,
  LoaderCircle,
  LockKeyhole,
  MessageSquare,
  Monitor,
  ShieldCheck,
  Sparkles,
  Trash2,
} from "lucide-react";
import ScreenshotReview from "./ScreenshotReview";
import GuidedDetails, { emptyGuidedAnswers, frequencyLabels, type GuidedAnswers } from "./GuidedDetails";
import { api, ApiError, type IssueWorkflow } from "./types";
import { activateCustomer, browserStorage } from "./browserStorage";
import NotificationBell from "./NotificationBell";
import Conversation from "./Conversation";
import { CustomerProgress } from "./WorkflowPanel";
import DeleteReportButton from "./DeleteReportButton";
import ArchiveReportButton from "./ArchiveReportButton";
import { rememberSubmission, forgetSubmission } from "./customerStorage";

type Context = {
  user_agent: string;
  language: string;
  timezone: string;
  viewport_width: number;
  viewport_height: number;
  screen_width: number;
  screen_height: number;
  source: "standalone" | "embedded" | "demo";
  same_browser_confirmed: boolean;
};
type Record = {
  access_token: string;
  account_owned: boolean;
  workflow: IssueWorkflow | null;
  intake_token: string;
  reference: string;
  project_name: string;
  team_name?: string;
  project_url: string;
  stage: string;
  reporter_name: string;
  text: string;
  guided_details: GuidedAnswers | null;
  draft_version: number;
  archived_at: string | null;
  page_url: string;
  context: Context;
  questions: string[];
  answers: { id: string; question: string; answer: string }[];
  attachments: {
    id: string;
    filename: string;
    width: number;
    height: number;
    analyzed: boolean;
  }[];
  processing_error: string | null;
  processing: boolean;
  has_report: boolean;
};
type Config = {
  project_name: string;
  team_name?: string;
  project_url: string;
  allowed_origin: string;
};
const browserContext = (): Context => ({
  user_agent: navigator.userAgent.slice(0, 500),
  language: navigator.language,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  viewport_width: innerWidth,
  viewport_height: innerHeight,
  screen_width: screen.width,
  screen_height: screen.height,
  source: "standalone",
  same_browser_confirmed: false,
});
const emptyContext: Context = {
  user_agent: "",
  language: "",
  timezone: "",
  viewport_width: 0,
  viewport_height: 0,
  screen_width: 0,
  screen_height: 0,
  source: "standalone",
  same_browser_confirmed: false,
};

export default function CustomerIntake({
  intakeToken,
  resumeToken,
}: {
  intakeToken?: string;
  resumeToken?: string;
}) {
  const embedded = new URLSearchParams(location.search).get("embedded") === "1";
  const [config, setConfig] = useState<Config | null>(null);
  const [record, setRecord] = useState<Record | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [draftConflict, setDraftConflict] = useState(false);
  const [unsavedCopy, setUnsavedCopy] = useState<ReturnType<typeof fields> | null>(null);
  const [busy, setBusy] = useState(false);
  const [working, setWorking] = useState("");
  const [text, setText] = useState("");
  const [guided, setGuided] = useState<GuidedAnswers>(emptyGuidedAnswers);
  const [pageUrl, setPageUrl] = useState("");
  const [name, setName] = useState("");
  const [context, setContext] = useState<Context>(browserContext);
  const [includeContext, setIncludeContext] = useState(false);
  const [consent, setConsent] = useState(false);
  const [step, setStep] = useState<"form" | "questions" | "review" | "receipt">(
    "form",
  );
  const [answers, setAnswers] = useState<{ [question: string]: string }>({});
  const [copied, setCopied] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const nonce = useRef(crypto.randomUUID());
  const signature = useRef("");
  const initialized = useRef(false);
  const accountIdentity = useRef<string | null>(null);
  const storageKey = `bugbrief-customer-${intakeToken || resumeToken}`;
  useEffect(() => {
    const checkAccount = () => {
      if (accountIdentity.current === null) return;
      api<{ customer?: { id: string } }>("/customer/session")
        .then((value) => {
          const identity = value.customer?.id || "guest";
          if (identity !== accountIdentity.current) {
            initialized.current = false;
            activateCustomer(identity);
            location.reload();
          }
        })
        .catch(() => {});
    };
    window.addEventListener("focus", checkAccount);
    return () => window.removeEventListener("focus", checkAccount);
  }, []);

  function adopt(value: Record, restore = false) {
    rememberSubmission(value);
    setRecord(value);
    setConfig({
      project_name: value.project_name,
      team_name: value.team_name,
      project_url: value.project_url,
      allowed_origin: value.project_url
        ? new URL(value.project_url).origin
        : "",
    });
    if (restore) {
      setText(value.text);
      setGuided(value.guided_details || emptyGuidedAnswers);
      setPageUrl(value.page_url);
      setName(value.reporter_name);
      setIncludeContext(!!value.context.user_agent);
      setContext(value.context.user_agent ? value.context : browserContext());
      signature.current = JSON.stringify({
        text: value.text,
        guided_details: value.guided_details || emptyGuidedAnswers,
        page_url: value.page_url,
        reporter_name: value.reporter_name,
        context: value.context,
      });
      setStep(
        value.stage === "submitted"
          ? "receipt"
          : value.questions.length
            ? "questions"
            : value.has_report
              ? "review"
              : "form",
      );
    }
  }
  useEffect(() => {
    let cancelled = false;
    async function initialize() {
      try {
        const session = await api<{
          authenticated: boolean;
          customer?: { id: string };
        }>("/customer/session");
        if (cancelled) return;
        accountIdentity.current = session.customer?.id || "guest";
        activateCustomer(accountIdentity.current);
        setSignedIn(session.authenticated);
        let saved: any = null;
        try {
          saved = JSON.parse(browserStorage.getItem(storageKey) || "null");
        } catch {}
        if (saved?.nonce) nonce.current = saved.nonce;
        if (saved?.answers) setAnswers(saved.answers);
        if (saved?.unsaved_copy) setUnsavedCopy(saved.unsaved_copy);
        let restored = false;
        if (resumeToken || saved?.access_token) {
          let value: Record | null = null;
          try {
            value = await api<Record>(`/public/submissions/${resumeToken || saved.access_token}`);
          } catch (error) {
            if (cancelled) return;
            if (!resumeToken && intakeToken && error instanceof ApiError && [404, 410].includes(error.status)) {
              // A removed report must not trap the reusable project form in its old draft.
              forgetSubmission(saved.access_token);
              browserStorage.removeItem(storageKey);
              nonce.current = crypto.randomUUID();
              saved = null;
              setAnswers({});
            } else throw error;
          }
          if (cancelled) return;
          if (value) {
            restored = true;
            adopt(value, true);
            if (value.stage !== "submitted" && saved) {
              if (saved.draft_version) setRecord({ ...value, draft_version: saved.draft_version });
              setText(saved.text ?? value.text);
              setGuided(saved.guided_details ?? value.guided_details ?? emptyGuidedAnswers);
              setIncludeContext(saved.includeContext ?? !!value.context.user_agent);
              setPageUrl(saved.page_url ?? value.page_url);
              setName(saved.name ?? value.reporter_name);
              if (saved.step) setStep(saved.step);
            }
          }
        }
        if (!restored && intakeToken) {
          const value = await api<Config>(`/public/intake/${intakeToken}`);
          if (cancelled) return;
          setConfig(value);
          if (saved) {
            setText(saved.text || "");
            setGuided(saved.guided_details || emptyGuidedAnswers);
            setPageUrl(saved.page_url || "");
            setName(saved.name || "");
            setIncludeContext(saved.includeContext === true);
          }
        }
        initialized.current = true;
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    initialize();
    return () => {
      cancelled = true;
    };
  }, [intakeToken, resumeToken]);
  useEffect(() => {
    if (!initialized.current || deleted) return;
    const value = JSON.stringify({
      nonce: nonce.current,
      access_token: record?.access_token,
      draft_version: record?.draft_version,
      unsaved_copy: unsavedCopy,
      text,
      guided_details: guided,
      page_url: pageUrl,
      name,
      includeContext,
      answers,
      step,
    });
    browserStorage.setItem(storageKey, value);
    if (record)
      browserStorage.setItem(`bugbrief-customer-${record.access_token}`, value);
  }, [
    record,
    unsavedCopy,
    text,
    guided,
    pageUrl,
    name,
    includeContext,
    answers,
    step,
    storageKey,
    deleted,
  ]);
  useEffect(() => {
    if (!config || !embedded) return;
    function receive(event: MessageEvent) {
      if (
        event.source !== parent ||
        !event.data ||
        event.data.type !== "bugbrief:context"
      )
        return;
      const data = event.data;
      let supplied: URL;
      try {
        supplied = new URL(data.pageUrl);
      } catch {
        return;
      }
      const token = intakeToken || record?.intake_token;
      const demo =
        event.origin === location.origin &&
        supplied.origin === location.origin &&
        supplied.pathname === `/demo/${token}`;
      if (
        !demo &&
        (event.origin !== config!.allowed_origin ||
          supplied.origin !== event.origin)
      )
        return;
      const width = Number(data.viewportWidth),
        height = Number(data.viewportHeight);
      if (
        !Number.isInteger(width) ||
        !Number.isInteger(height) ||
        width < 1 ||
        height < 1 ||
        width > 20000 ||
        height > 20000
      )
        return;
      setContext((previous) => ({
        ...previous,
        source: demo ? "demo" : "embedded",
        viewport_width: width,
        viewport_height: height,
      }));
      setPageUrl((previous) => previous || supplied.origin + supplied.pathname);
    }
    window.addEventListener("message", receive);
    parent.postMessage({ type: "bugbrief:ready" }, "*");
    return () => window.removeEventListener("message", receive);
  }, [config?.allowed_origin, embedded, intakeToken, record?.intake_token]);
  useEffect(() => {
    if (!record?.processing) return;
    setBusy(true);
    setWorking("Checking the saved details");
    const timer = setInterval(async () => {
      try {
        const value = await api<Record>(
          `/public/submissions/${record.access_token}`,
        );
        adopt(value);
        if (!value.processing) {
          setBusy(false);
          setWorking("");
          setStep(value.questions.length ? "questions" : "review");
        }
      } catch (e) {
        setError((e as Error).message);
        setBusy(false);
        setRecord((previous) =>
          previous ? { ...previous, processing: false } : null,
        );
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [record?.access_token, record?.processing]);
  useEffect(() => {
    if (!record || record.stage !== "submitted" || deleted) return;
    const refresh = () =>
      api<Record>(`/public/submissions/${record.access_token}`)
        .then((value) => adopt(value))
        .catch((e) => {
          setError(e.message);
          if ([401, 403, 404].includes(e.status)) {
            initialized.current = false;
            setText("");
            setGuided(emptyGuidedAnswers);
            setName("");
            setAnswers({});
            setRecord(null);
            setConfig(null);
          }
        });
    const timer = setInterval(refresh, 15000);
    window.addEventListener("focus", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [record?.access_token, record?.stage, deleted]);
  function fields() {
    return {
      text,
      guided_details: guided,
      page_url: pageUrl.trim(),
      reporter_name: name.trim(),
      context: includeContext ? context : emptyContext,
    };
  }
  async function ensureSaved(checkVersion = false) {
    if (draftConflict) throw new Error("Load the latest draft before saving. Your unsaved answers are still here.");
    if (pageUrl.trim() && !/^https?:\/\//.test(pageUrl.trim()))
      throw new Error("Use a full page URL starting with https:// or http://.");
    const draft = fields();
    const current = JSON.stringify(draft);
    if (record) {
      if (current === signature.current && !checkVersion) return record;
      let value: Record;
      try { value = await api<Record>(
        `/public/submissions/${record.access_token}`,
        "PUT",
        { ...draft, draft_version: record.draft_version },
      ); } catch (e) {
        if (e instanceof ApiError && e.status === 409 && e.message.includes("already with the agency")) {
          const sent = await api<Record>(`/public/submissions/${record.access_token}`);
          if (sent.stage === "submitted") { adopt(sent, true); return sent; }
        }
        if (e instanceof ApiError && [409, 428].includes(e.status) && /Draft changed|draft version/.test(e.message)) setDraftConflict(true);
        throw e;
      }
      adopt(value);
      signature.current = current;
      return value;
    }
    const token = intakeToken;
    if (!token) throw new Error("This project link is unavailable.");
    let value = await api<Record>(
      `/public/intake/${token}/submissions`,
      "POST",
      { ...draft, client_nonce: nonce.current },
    );
    // A retry can recover an earlier save whose response was lost.
    const changed = Object.entries(draft).some(
      ([key, expected]) =>
        JSON.stringify(value[key as keyof Record]) !== JSON.stringify(expected),
    );
    if (changed && value.stage !== "submitted") {
      value = await api<Record>(
        `/public/submissions/${value.access_token}`,
        "PUT",
        { ...draft, draft_version: value.draft_version },
      );
    }
    adopt(value);
    signature.current = current;
    browserStorage.setItem(
      storageKey,
      JSON.stringify({
        nonce: nonce.current,
        access_token: value.access_token,
        draft_version: value.draft_version,
        unsaved_copy: unsavedCopy,
        text,
        guided_details: guided,
        page_url: pageUrl,
        name,
        includeContext,
      }),
    );
    history.replaceState(
      null,
      "",
      `/s/${value.access_token}${embedded ? "?embedded=1" : ""}`,
    );
    return value;
  }
  async function act(label: string, operation: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setWorking(label);
    setError("");
    try {
      await operation();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setWorking("");
    }
  }
  async function attach(blob: Blob, filename: string) {
    setError("");
    setBusy(true);
    try {
      const current = await ensureSaved(true);
      const response = await fetch(
        `/api/public/submissions/${current.access_token}/attachments?reviewed=true&filename=${encodeURIComponent(filename)}`,
        { method: "POST", headers: { "Content-Type": blob.type }, body: blob },
      );
      const data = await response.json();
      if (!response.ok)
        throw new Error(data.detail || "Could not save the screenshot.");
      adopt(data);
    } finally {
      setBusy(false);
    }
  }
  async function prepare() {
    await act("Checking the details", async () => {
      let current = await ensureSaved();
      if (consent) {
        current = await api<Record>(
          `/public/submissions/${current.access_token}/process`,
          "POST",
          { consent: true },
        );
        adopt(current);
      }
      setStep(current.questions.length ? "questions" : "review");
    });
  }
  async function answerQuestions() {
    await act("Saving your answers", async () => {
      if (!record) return;
      const batch = record.questions
        .filter((question) => answers[question]?.trim())
        .map((question) => ({ question, answer: answers[question].trim() }));
      let current = record;
      if (batch.length) {
        current = await api<Record>(
          `/public/submissions/${record.access_token}/answers`,
          "POST",
          { answers: batch },
        );
        adopt(current);
      }
      if (consent && batch.length) {
        setWorking("Updating the brief");
        current = await api<Record>(
          `/public/submissions/${record.access_token}/process`,
          "POST",
          { consent: true },
        );
        adopt(current);
      }
      setStep("review");
    });
  }
  async function send() {
    await act("Sending to the agency", async () => {
      const current = await ensureSaved(true);
      const value = await api<Record>(
        `/public/submissions/${current.access_token}/submit`,
        "POST",
        {},
      );
      adopt(value);
      setStep("receipt");
    });
  }
  function fresh() {
    browserStorage.removeItem(storageKey);
    location.assign(
      `/c/${record?.intake_token || intakeToken}${embedded ? "?embedded=1" : ""}`,
    );
  }
  const privateUrl = record
    ? `${location.origin}/s/${record.access_token}`
    : "";
  if (deleted)
    return (
      <div className="customer-unavailable">
        <CheckCheck size={32} />
        <h1>Your report has been deleted.</h1>
        <p>
          Your feedback, screenshots and answers have been removed from the
          workspace.
        </p>
        <a className="primary-button" href="/customer">
          Back to your reports
        </a>
      </div>
    );
  if (loading)
    return (
      <div className="customer-loading">
        <LoaderCircle className="spin" size={20} />
        Opening your feedback link…
      </div>
    );
  if (!config)
    return (
      <div className="customer-unavailable">
        <ShieldCheck size={29} />
        <h1>
          {(resumeToken || intakeToken) && error.includes("Sign in")
            ? "Sign in to view your report."
            : "This feedback link is unavailable."}
        </h1>
        <p>{error || "Ask the agency for a new project link."}</p>
        {(resumeToken || intakeToken) && error.includes("Sign in") && (
          <a
            className="primary-button"
            href={`/customer/signin?next=${encodeURIComponent(resumeToken ? `/s/${resumeToken}` : `/c/${intakeToken}`)}`}
            target={embedded ? "_blank" : undefined}
            rel="noreferrer"
          >
            Customer sign in
          </a>
        )}
        <a className="secondary-button" href="/customer">
          Back to your reports
        </a>
      </div>
    );
  return (
    <div className={`customer-shell ${embedded ? "in-widget" : ""}`}>
      <header className="customer-header">
        <a
          href={location.pathname}
          onClick={(event) => event.preventDefault()}
          className="customer-brand"
        >
          b<span>✳</span> bugbrief
        </a>
        <span>
          <LockKeyhole size={12} />
          Private project feedback
        </span>
        {signedIn && <NotificationBell audience="customer" />}
        {!embedded && (
          <a className="portal-back" href="/customer">
            Your reports / switch role
          </a>
        )}
      </header>
      <main className="customer-main">
        <div className="customer-project">
          <span>{config.project_name.slice(0, 1).toUpperCase()}</span>
          <div>
            <small>FEEDBACK FOR</small>
            <strong>{config.project_name}</strong>
            <small>Managed by {config.team_name || "your project team"}</small>
          </div>
          <span className="customer-project-tag">CUSTOMER PORTAL</span>
        </div>
        {!record && (
          <div className="customer-signin-note">
            {signedIn ? (
              "This report will be saved to your customer account."
            ) : (
              <>
                Have an account?{" "}
                <a
                  target={embedded ? "_blank" : undefined}
                  rel="noopener noreferrer"
                  href={`/customer/signin?next=${encodeURIComponent(`/c/${intakeToken}`)}`}
                >
                  Sign in
                </a>{" "}
                to keep this report with your others. New here?{" "}
                <a
                  target={embedded ? "_blank" : undefined}
                  rel="noopener noreferrer"
                  href={`/customer/signup?next=${encodeURIComponent(`/c/${intakeToken}`)}`}
                >
                  Create an account
                </a>
                .
              </>
            )}
          </div>
        )}
        {step !== "receipt" && (
          <div className="customer-progress">
            <span className={step === "form" ? "current" : "complete"}>
              <i>{step === "form" ? "1" : <Check size={10} />}</i>Describe
            </span>
            <b />
            <span
              className={
                step === "questions"
                  ? "current"
                  : step === "review"
                    ? "complete"
                    : ""
              }
            >
              <i>{step === "review" ? <Check size={10} /> : "2"}</i>Add details
            </span>
            <b />
            <span className={step === "review" ? "current" : ""}>
              <i>3</i>Send
            </span>
          </div>
        )}
        {error && (
          <div className="alert error" role="alert">
            {error}
          </div>
        )}
        {draftConflict && record && <div className="draft-conflict" role="alert">
          <h3>This draft changed in another tab.</h3>
          <p>Your answers have not been replaced. Load the latest saved draft to compare; your unsaved copy will remain available below.</p>
          <button className="secondary-button" disabled={busy} onClick={() => act("Loading latest draft", async () => {
            const latest = await api<Record>(`/public/submissions/${record.access_token}`);
            setUnsavedCopy(fields()); adopt(latest, true); setDraftConflict(false);
          })}>Load latest draft</button>
        </div>}
        {unsavedCopy && <details className="draft-conflict"><summary>Your unsaved copy</summary>
          <p>{unsavedCopy.text}</p><GuidedDetails details={unsavedCopy.guided_details} />
          <p>{unsavedCopy.page_url}</p>
          <button className="secondary-button" disabled={busy || record?.stage === "submitted"} onClick={() => {
            setText(unsavedCopy.text); setGuided(unsavedCopy.guided_details); setPageUrl(unsavedCopy.page_url);
            setName(unsavedCopy.reporter_name); setContext(unsavedCopy.context); setIncludeContext(!!unsavedCopy.context.user_agent);
            setStep("form"); setUnsavedCopy(null);
          }}>Use my copy for editing</button><p>Review before saving. Saving will replace the latest draft answers.</p>
        </details>}
        {busy && (
          <div className="customer-working" role="status">
            <LoaderCircle className="spin" size={17} />
            <span>
              {working || "Saving your work"}…
              <small>Your original feedback stays saved.</small>
            </span>
          </div>
        )}
        {step === "form" && (
          <>
            <div className="customer-intro">
              <span className="eyebrow">LET’S GET IT SORTED</span>
              <h1>Something not quite right?</h1>
              <p>
                Tell us what happened. We’ll collect the details so your team
                can get to the fix sooner.
              </p>
            </div>
            <section className="customer-form-card">
              <p className="guided-intro">A few short answers help the team reproduce the problem. Describe what happened, then add whatever else you know. The other details are optional.</p>
              <label>
                What were you trying to do?
                <input
                  aria-label="What were you trying to do?"
                  maxLength={1000}
                  disabled={busy}
                  value={guided.goal}
                  onChange={(event) => setGuided({ ...guided, goal: event.target.value })}
                  placeholder="e.g. Complete my order"
                />
              </label>
              <label>
                What went wrong?
                <textarea
                  rows={5}
                  disabled={busy}
                  maxLength={8000}
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder="e.g. I clicked Pay now, but nothing happened. I expected the payment form to open."
                />
              </label>
              <div className="customer-language">
                <Globe size={13} />
                English, हिंदी, or a little of both.
                <span>{text.length} / 8,000</span>
              </div>
              <label>
                What did you expect to happen?
                <textarea
                  aria-label="What did you expect to happen?"
                  rows={2}
                  maxLength={2000}
                  disabled={busy}
                  value={guided.expected}
                  onChange={(event) => setGuided({ ...guided, expected: event.target.value })}
                  placeholder="e.g. The payment form should open"
                />
              </label>
              <label>
                How often does it happen?
                <select
                  aria-label="How often does it happen?"
                  disabled={busy}
                  value={guided.frequency}
                  onChange={(event) => setGuided({ ...guided, frequency: event.target.value as GuidedAnswers["frequency"] })}
                >
                  <option value="">Choose if you know</option>
                  {Object.entries(frequencyLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              <details className="guided-steps" open={!!guided.steps || undefined}>
                <summary>Add the steps you took <span className="optional">optional</span></summary>
                <label>
                  Steps you took
                  <textarea
                    aria-label="Steps you took"
                    rows={3}
                    maxLength={2000}
                    disabled={busy}
                    value={guided.steps}
                    onChange={(event) => setGuided({ ...guided, steps: event.target.value })}
                    placeholder={"1. Opened my cart\n2. Entered my address\n3. Clicked Pay now"}
                  />
                </label>
              </details>
              <label>
                Where did it happen?
                <input
                  type="url"
                  disabled={busy}
                  maxLength={2000}
                  value={pageUrl}
                  onChange={(event) => setPageUrl(event.target.value)}
                  placeholder={
                    config.project_url || "https://example.com/checkout"
                  }
                />
              </label>
              {context.source !== "standalone" && (
                <span className="context-captured">
                  <Check size={12} />
                  Page URL captured from{" "}
                  {context.source === "demo"
                    ? "the demo preview"
                    : "the website"}{" "}
                  · query strings excluded
                </span>
              )}
              <label>
                Your name{" "}
                <span className="optional">optional · for the agency only</span>
                <input
                  maxLength={80}
                  disabled={busy}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="How should the team refer to you?"
                />
              </label>
              <div className="customer-images">
                <div className="evidence-section-title">
                  <Image size={16} />
                  <h3>A screenshot helps.</h3>
                  <span>{record?.attachments.length || 0} / 3</span>
                </div>
                <p className="evidence-copy">
                  Cover private details before saving. Screenshots stay with
                  this submission.
                </p>
                {record?.attachments.map((image) => (
                  <div className="customer-attachment" key={image.id}>
                    <img
                      alt={`Reviewed screenshot: ${image.filename}`}
                      src={`/api/public/submissions/${record.access_token}/attachments/${image.id}/content`}
                    />
                    <span>
                      {image.filename}
                      <small>
                        {image.width} × {image.height} · Reviewed
                      </small>
                    </span>
                    <button
                      className="icon-button"
                      aria-label={`Delete screenshot ${image.filename}`}
                      disabled={busy}
                      onClick={() =>
                        act("Removing screenshot", async () => {
                          const value = await api<Record>(
                            `/public/submissions/${record.access_token}/attachments/${image.id}`,
                            "DELETE",
                          );
                          adopt(value);
                        })
                      }
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                ))}
                {(!record || record.attachments.length < 3) && (
                  <ScreenshotReview
                    busy={busy}
                    onSave={attach}
                    onError={setError}
                  />
                )}
              </div>
              <div className="customer-context">
                <div className="context-heading">
                  <Monitor size={17} />
                  <h3>Skip the “which browser?” message.</h3>
                </div>
                <p>
                  We can include this browser’s details. No cookies, passwords
                  or browsing history are collected.
                </p>
                <label className="customer-check">
                  <input
                    type="checkbox"
                    disabled={busy}
                    checked={includeContext}
                    onChange={(event) =>
                      setIncludeContext(event.target.checked)
                    }
                  />
                  <span>
                    Include browser, language, timezone and screen dimensions
                  </span>
                </label>
                {includeContext && (
                  <>
                    <div className="context-summary">
                      <span>
                        <strong>Viewport</strong>
                        {context.viewport_width} × {context.viewport_height}
                      </span>
                      <span>
                        <strong>Language</strong>
                        {context.language}
                      </span>
                      <span>
                        <strong>Source</strong>
                        {context.source === "standalone"
                          ? "This form"
                          : context.source === "demo"
                            ? "Demo preview"
                            : "Affected website"}
                      </span>
                    </div>
                    <label className="customer-check">
                      <input
                        type="checkbox"
                        disabled={busy}
                        checked={context.same_browser_confirmed}
                        onChange={(event) =>
                          setContext({
                            ...context,
                            same_browser_confirmed: event.target.checked,
                          })
                        }
                      />
                      <span>
                        This is the browser I used when the issue happened.
                      </span>
                    </label>
                    <small>
                      Until you confirm, these details are only submission
                      context.
                    </small>
                  </>
                )}
              </div>
              <div className="customer-ai-consent">
                <Sparkles size={17} />
                <div>
                  <strong>Catch the missing details now.</strong>
                  <p>
                    Optional: Gemini can check your description and reviewed
                    screenshots for useful follow-up questions. Free-tier inputs
                    and outputs may be used for product improvement and human
                    review. Remove sensitive information first.
                  </p>
                  <label className="customer-check">
                    <input
                      type="checkbox"
                      disabled={busy}
                      checked={consent}
                      onChange={(event) => setConsent(event.target.checked)}
                    />
                    <span>
                      I agree to this external processing of my saved feedback
                      and evidence.
                    </span>
                  </label>
                </div>
              </div>
              <button
                className="primary-button customer-primary"
                disabled={busy || (!text.trim() && !record?.attachments.length)}
                onClick={prepare}
              >
                {consent ? <Sparkles size={16} /> : <ArrowRight size={16} />}
                Continue{consent ? " with a quick check" : ""}
                <ArrowRight size={16} />
              </button>
              <p className="customer-reassurance">
                <ShieldCheck size={13} />
                You can send your feedback even if the automatic check is
                unavailable.
              </p>
            </section>
          </>
        )}
        {step === "questions" && record && (
          <>
            <div className="customer-intro">
              <span className="eyebrow">A LITTLE CONTEXT GOES A LONG WAY</span>
              <h1>A couple of quick details.</h1>
              <p>
                Answer what you know. These questions help the team act without
                another round of messages.
              </p>
            </div>
            {record.processing_error && (
              <div className="customer-notice">{record.processing_error}</div>
            )}
            <section className="customer-form-card">
              <div className="customer-original">
                <MessageSquare size={16} />
                <p>{record.text || "You attached a reviewed screenshot."}</p>
              </div>
              {record.questions.map((question, index) => (
                <div className="customer-question" key={question}>
                  <label>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    {question}
                    <textarea
                      rows={3}
                      disabled={busy}
                      maxLength={2000}
                      value={answers[question] || ""}
                      onChange={(event) =>
                        setAnswers({
                          ...answers,
                          [question]: event.target.value,
                        })
                      }
                    />
                  </label>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() =>
                      setAnswers({ ...answers, [question]: "I’m not sure." })
                    }
                  >
                    I’m not sure
                  </button>
                </div>
              ))}
              <button
                className="primary-button customer-primary"
                disabled={busy}
                onClick={answerQuestions}
              >
                Save details & review
                <ArrowRight size={16} />
              </button>
              <button
                className="customer-skip"
                disabled={busy}
                onClick={() => setStep("review")}
              >
                Skip these questions and review
              </button>
            </section>
          </>
        )}
        {step === "review" && record && (
          <>
            <div className="customer-intro">
              <span className="eyebrow">ONE CLEAR HANDOFF</span>
              <h1>Ready for the team?</h1>
              <p>
                Your feedback and evidence will arrive together. The agency
                reviews the report before acting on it.
              </p>
            </div>
            {record.processing_error && (
              <div className="customer-notice" role="status">
                {record.processing_error}
              </div>
            )}
            <section className="customer-form-card">
              <div className="customer-review-label">
                <CheckCheck size={18} />
                {record.has_report
                  ? "A draft brief is prepared for agency review."
                  : "Your original feedback is ready for manual review."}
              </div>
              <div className="customer-original">
                <MessageSquare size={16} />
                <p>{record.text || "Screenshot feedback"}</p>
              </div>
              <GuidedDetails details={record.guided_details} />
              <dl className="customer-review-details">
                <div>
                  <dt>Affected page</dt>
                  <dd>{record.page_url || "Not supplied"}</dd>
                </div>
                <div>
                  <dt>Screenshots</dt>
                  <dd>{record.attachments.length} reviewed</dd>
                </div>
                <div>
                  <dt>Clarification answers</dt>
                  <dd>{record.answers.length} saved</dd>
                </div>
                <div>
                  <dt>Browser details</dt>
                  <dd>
                    {record.context.user_agent
                      ? record.context.same_browser_confirmed
                        ? "Included · customer confirmed"
                        : "Included · issue browser unconfirmed"
                      : "Not included"}
                  </dd>
                </div>
              </dl>
              {record.questions.length > 0 && (
                <div className="customer-open-questions">
                  <strong>
                    {record.questions.length} unanswered detail
                    {record.questions.length > 1 ? "s" : ""}
                  </strong>
                  <p>That’s okay. The team will see what is still unknown.</p>
                  <button
                    className="text-button"
                    onClick={() => setStep("questions")}
                  >
                    Answer what you can <ArrowRight size={13} />
                  </button>
                </div>
              )}
              <button
                className="primary-button customer-primary"
                disabled={busy}
                onClick={send}
              >
                <Check size={16} />
                Send to the agency
                <ArrowRight size={16} />
              </button>
              <button
                className="customer-skip"
                disabled={busy}
                onClick={() => setStep("form")}
              >
                <ChevronLeft size={13} />
                Edit your feedback
              </button>
            </section>
          </>
        )}
        {step === "receipt" && record && (
          <section className="customer-receipt">
            <span className="receipt-check">
              <CheckCheck size={33} />
            </span>
            <span className="eyebrow">ALL TOGETHER. ALL SENT.</span>
            <h1>
              {record.workflow?.status === "resolved"
                ? "Your issue is marked resolved."
                : record.workflow?.status === "ready_to_retest"
                  ? "A fix is ready to try."
                  : "The team has your feedback."}
            </h1>
            <p>
              Your words, screenshots and saved answers are together in the
              agency’s review inbox.
            </p>
            <div className="receipt-reference">
              <span>YOUR REFERENCE</span>
              <strong>BB-{record.reference}</strong>
              <small>{record.project_name}</small>
            </div>
            {record.workflow && (
              <CustomerProgress
                workflow={record.workflow}
                token={record.access_token}
                onChange={(workflow) =>
                  setRecord((previous) =>
                    previous ? { ...previous, workflow } : previous,
                  )
                }
              />
            )}
            <Conversation
              key={record.access_token}
              token={record.access_token}
            />
            <p>Archiving hides this report from your active list. The company can still reply, and you can restore it anytime.</p>
            {record.archived_at && <p className="customer-notice">This report is archived in your list.</p>}
            <ArchiveReportButton endpoint={`/public/submissions/${record.access_token}`} archived={!!record.archived_at} onChange={value => adopt(value)} />
            <div className="receipt-next">
              <span>01</span>
              <p>The agency reviews the details and any remaining unknowns.</p>
              <span>02</span>
              <p>
                A developer gets the reviewed brief. This receipt doesn’t
                promise a fix or a response time.
              </p>
            </div>
            {record.account_owned ? (
              <div className="customer-notice">
                Saved to your account. You can find this report whenever you
                sign in.
              </div>
            ) : (
              <>
                <label className="receipt-link">
                  Keep your private return link
                  <input readOnly value={privateUrl} />
                </label>
                <button
                  className="secondary-button full-width"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(privateUrl);
                      setCopied(true);
                    } catch {
                      setError(
                        "Select and copy the private return link above.",
                      );
                    }
                  }}
                >
                  {copied ? <Check size={15} /> : <Copy size={15} />}{" "}
                  {copied ? "Private link copied" : "Copy private return link"}
                </button>
                <small className="receipt-private">
                  <LockKeyhole size={11} />
                  Anyone with this link can view this submission. Keep it
                  private.
                </small>
              </>
            )}
            <button className="customer-skip" onClick={fresh}>
              Report another issue <ArrowRight size={13} />
            </button>
          </section>
        )}
        {record && !record.account_owned && (
          <aside className="customer-account-invite">
            <h3>Keep your reports in one place.</h3>
            <p>
              Save this report to an account so you can find it by signing in
              next time.
            </p>
            <a
              className="primary-button"
              target={embedded ? "_blank" : undefined}
              rel="noopener noreferrer"
              href={`/customer/signup?next=${encodeURIComponent(`/s/${record.access_token}`)}`}
            >
              Create an account
            </a>
            <a
              className="portal-back"
              target={embedded ? "_blank" : undefined}
              rel="noopener noreferrer"
              href={`/customer/signin?next=${encodeURIComponent(`/s/${record.access_token}`)}`}
            >
              Already a customer? Sign in
            </a>
          </aside>
        )}
        {record && record.account_owned && (
          <p className="customer-account-saved">
            <a href="/customer">View all your reports in your account →</a>
          </p>
        )}
        {record && (
          <div className="customer-manage-report">
            {!embedded && (
              <a className="portal-back" href="/customer">
                ← Your reports
              </a>
            )}
            <DeleteReportButton
              customer
              disabled={busy}
              onDelete={async () => {
                await api(
                  `/public/submissions/${record.access_token}`,
                  "DELETE",
                );
                forgetSubmission(record.access_token);
                browserStorage.removeItem(storageKey);
                setDeleted(true);
              }}
            />
          </div>
        )}
      </main>
      <footer className="customer-footer">
        <span>b✳</span> A little clarity. A better handoff.
        <span>Powered by BugBrief</span>
      </footer>
    </div>
  );
}
