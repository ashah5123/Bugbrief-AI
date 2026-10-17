import {
  useEffect,
  useContext,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  FileCheck2,
  FileText,
  Folder,
  FolderOpen,
  Globe,
  Inbox,
  LayoutGrid,
  Lightbulb,
  Link2,
  LoaderCircle,
  Menu,
  MessageSquare,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  SquarePen,
  WandSparkles,
  X,
} from "lucide-react";
import EvidencePanel from "./EvidencePanel";
import ShareProject from "./ShareProject";
import CustomerContext from "./CustomerContext";
import DeleteReportButton from "./DeleteReportButton";
import WorkflowPanel, { WorkflowBadge, workflowLabels } from "./WorkflowPanel";
import { EmployeeContext } from "./AgencyGate";
import {
  api,
  type Feedback,
  type IssueWorkflow,
  type IssueEmployee,
  type Health,
  type Project,
  type Report,
  type Claim,
} from "./types";

type View = "overview" | "feedback" | "reports" | "projects";
type Draft = {
  project_id: string;
  text: string;
  page_url: string;
  device: string;
  browser: string;
};
const emptyDraft: Draft = {
  project_id: "",
  text: "",
  page_url: "",
  device: "",
  browser: "",
};
const example =
  "On the checkout page, I added a product to my cart and clicked “Pay now”. Nothing happened after clicking the button. I expected to see the payment form.";
function readDraft(): Draft {
  try {
    return {
      ...emptyDraft,
      ...JSON.parse(localStorage.getItem("bugbrief-draft") || "{}"),
    };
  } catch {
    return emptyDraft;
  }
}
function dateLabel(date: string) {
  return new Date(date).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
  });
}

function Modal({
  title,
  subtitle,
  children,
  close,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prior = document.activeElement as HTMLElement;
    ref.current?.querySelector<HTMLElement>("input, button, textarea")?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {
        const items = ref.current?.querySelectorAll<HTMLElement>(
          "button, input, textarea, select, a[href]",
        );
        if (!items?.length) return;
        const first = items[0],
          last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      prior?.focus();
    };
  }, [close]);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={ref}
      >
        <button
          className="icon-button modal-close"
          aria-label="Close dialog"
          onClick={close}
        >
          <X size={20} />
        </button>
        <span className="eyebrow">YOUR WORKSPACE</span>
        <h2>{title}</h2>
        {subtitle && <p className="muted">{subtitle}</p>}
        {children}
      </div>
    </div>
  );
}

export default function App() {
  const employee = useContext(EmployeeContext);
  const userInitial = employee?.name.slice(0, 1).toUpperCase() || "W";
  const [manualOpen, setManualOpen] = useState(() =>
    Boolean(localStorage.getItem("bugbrief-active-id")),
  );
  const [sharing, setSharing] = useState<string | null>(null);
  const [view, setView] = useState<View>("overview");
  const [projects, setProjects] = useState<Project[]>([]);
  const [employees, setEmployees] = useState<IssueEmployee[]>([]);
  const [progressFilter, setProgressFilter] = useState("all");
  const [assigneeFilter, setAssigneeFilter] = useState("all");
  const [items, setItems] = useState<Feedback[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [draft, setDraft] = useState<Draft>(readDraft);
  const [activeId, setActiveId] = useState<string | null>(() =>
    localStorage.getItem("bugbrief-active-id"),
  );
  const [projectFilter, setProjectFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [modal, setModal] = useState<"project" | "settings" | "guide" | null>(
    null,
  );
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [consent, setConsent] = useState(false);
  const [showContext, setShowContext] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [selected, setSelected] = useState<Feedback | null>(null);
  const [editReport, setEditReport] = useState<Report | null>(null);
  const [editorTab, setEditorTab] = useState<"report" | "source" | "evidence">(
    "report",
  );
  const composer = useRef<HTMLTextAreaElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!selected) return;
    const prior = document.activeElement as HTMLElement;
    drawerRef.current?.querySelector<HTMLElement>("button")?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const controls = drawerRef.current?.querySelectorAll<HTMLElement>(
        "button:not(:disabled), input, textarea, select, summary",
      );
      if (!controls?.length) return;
      const first = controls[0],
        last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      prior?.focus();
    };
  }, [!!selected]);
  const closeModal = useRef(() => setModal(null)).current;
  const closeSharing = useRef(() => setSharing(null)).current;
  useEffect(() => {
    if (!modal && !selected) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [modal, !!selected]);

  async function refresh() {
    const [p, f, h, e] = await Promise.all([
      api<Project[]>("/projects"),
      api<Feedback[]>("/feedback"),
      api<Health>("/health"),
      api<IssueEmployee[]>("/employees"),
    ]);
    setProjects(p);
    setItems(f);
    setHealth(h);
    setEmployees(e);
    setDraft((d) =>
      d.project_id || !p.length ? d : { ...d, project_id: p[0].id },
    );
  }
  useEffect(() => {
    refresh()
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    localStorage.setItem("bugbrief-draft", JSON.stringify(draft));
  }, [draft]);
  useEffect(() => {
    if (activeId) localStorage.setItem("bugbrief-active-id", activeId);
    else localStorage.removeItem("bugbrief-active-id");
  }, [activeId]);
  useEffect(() => {
    if (notice) {
      const t = setTimeout(() => setNotice(""), 5000);
      return () => clearTimeout(t);
    }
  }, [notice]);
  useEffect(() => {
    if (!selected) return;
    const key = `bugbrief-report-${selected.id}`;
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "null");
      setEditReport(
        saved?.version === selected.version ? saved.report : selected.report,
      );
    } catch {
      setEditReport(selected.report);
    }
  }, [selected]);
  useEffect(() => {
    if (selected && editReport)
      localStorage.setItem(
        `bugbrief-report-${selected.id}`,
        JSON.stringify({ version: selected.version, report: editReport }),
      );
  }, [editReport, selected]);
  const activeFeedback = items.find((item) => item.id === activeId) || null;
  const hasSavedEvidence = !!(
    activeFeedback?.attachments.length || activeFeedback?.clarifications.length
  );
  const imagesNeedAnalysis = !!activeFeedback?.attachments.some(
    (image) => !image.analysis,
  );
  const evidenceLabels: Record<string, string> = {
    feedback: "Original feedback",
    page_url: "Page URL",
    device: "Device",
    browser: "Browser",
    captured_context: "Captured submission context",
  };
  selected?.clarifications.forEach((entry, index) => {
    evidenceLabels[`clarification:${entry.id}`] =
      `Clarification answer ${index + 1}`;
  });
  selected?.attachments.forEach((image, index) =>
    image.analysis?.observations.forEach((observation, observationIndex) => {
      evidenceLabels[`screenshot:${image.id}:${observationIndex}`] =
        `Screenshot ${index + 1}, observation ${observationIndex + 1} · unverified`;
    }),
  );
  useEffect(() => {
    const reload = () => {
      if (document.visibilityState === "visible") refresh().catch(() => {});
    };
    const interval = setInterval(reload, 15000);
    document.addEventListener("visibilitychange", reload);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", reload);
    };
  }, []);
  const reports = items.filter((i) => i.report);
  function evidenceUpdated(updated: Feedback) {
    setItems((current) =>
      current.some((item) => item.id === updated.id)
        ? current.map((item) => (item.id === updated.id ? updated : item))
        : [updated, ...current],
    );
    if (selected?.id === updated.id) setSelected(updated);
    api<Health>("/health")
      .then(setHealth)
      .catch(() => {});
  }
  async function preserveSelectedReport(): Promise<Feedback> {
    if (!selected) throw new Error("Open a report first.");
    if (!editReport) return selected;
    const saved = await api<Feedback>(
      `/feedback/${selected.id}/report`,
      "PUT",
      { version: selected.version, report: editReport },
    );
    setSelected(saved);
    return saved;
  }
  const ready =
    health?.ai_configured &&
    health.free_tier_confirmed &&
    !health.usage.paused &&
    health.usage.attempts < health.usage.limit;
  const filtered = items.filter(
    (i) =>
      (view !== "reports" || i.report) &&
      (projectFilter === "all" || i.project_id === projectFilter) &&
      (statusFilter === "all" || i.status === statusFilter) &&
      (progressFilter === "all" || i.workflow.status === progressFilter) &&
      (assigneeFilter === "all" ||
        (assigneeFilter === "unassigned"
          ? !i.workflow.assigned_employee_id
          : i.workflow.assigned_employee_id === assigneeFilter)) &&
      `${i.text} ${i.report?.title || ""}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  function navigate(next: View) {
    setView(next);
    setMobileNav(false);
    setSearch("");
    setStatusFilter("all");
    setProgressFilter("all");
    setAssigneeFilter("all");
  }
  function updateWorkflow(feedbackId: string, value: IssueWorkflow) {
    setItems((existing) =>
      existing.map((item) =>
        item.id === feedbackId ? { ...item, workflow: value } : item,
      ),
    );
    setSelected((existing) =>
      existing?.id === feedbackId ? { ...existing, workflow: value } : existing,
    );
  }
  function newFeedback() {
    setManualOpen(true);
    navigate("feedback");
    composer.current?.focus();
    setTimeout(() => composer.current?.focus(), 30);
  }
  async function deleteReport(item: Feedback) {
    await api(`/feedback/${item.id}`, "DELETE");
    localStorage.removeItem(`bugbrief-report-${item.id}`);
    if (selected?.id === item.id) setSelected(null);
    if (activeId === item.id) {
      setActiveId(null);
      setDraft({ ...emptyDraft, project_id: item.project_id });
    }
    await refresh();
    setNotice("Report and its evidence deleted.");
  }
  async function saveDraft(): Promise<Feedback> {
    if (!draft.project_id) {
      setModal("project");
      throw new Error("Create a project first. Your feedback is kept.");
    }
    const item = await api<Feedback>(
      activeId ? `/feedback/${activeId}` : "/feedback",
      activeId ? "PUT" : "POST",
      draft,
    );
    setActiveId(item.id);
    await refresh();
    return item;
  }
  async function submit(generate: boolean) {
    setError("");
    setBusy(true);
    try {
      const item = await saveDraft();
      if (generate) {
        const result = await api<Feedback>(
          `/feedback/${item.id}/generate`,
          "POST",
          { consent },
        );
        setSelected(result);
        setEditorTab("report");
        await refresh();
        setNotice("Your AI report is ready for review.");
      } else setNotice("Feedback saved. Pick it up whenever you’re ready.");
    } catch (e) {
      setError((e as Error).message);
      await refresh().catch(() => {});
    } finally {
      setBusy(false);
    }
  }
  async function regenerate() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      // Save unsaved edits first, so a proposed revision can never replace them silently.
      let current = selected;
      if (editReport)
        current = await api<Feedback>(
          `/feedback/${selected.id}/report`,
          "PUT",
          { version: selected.version, report: editReport },
        );
      setSelected(current);
      const result = await api<Feedback>(
        `/feedback/${selected.id}/generate`,
        "POST",
        { consent },
      );
      setSelected(result);
      await refresh();
      setNotice("New AI proposal ready. Your edits are preserved.");
    } catch (e) {
      setError((e as Error).message);
      await refresh().catch(() => {});
    } finally {
      setBusy(false);
    }
  }
  async function saveReport() {
    if (!selected || !editReport) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<Feedback>(
        `/feedback/${selected.id}/report`,
        "PUT",
        { version: selected.version, report: editReport },
      );
      setSelected(result);
      localStorage.removeItem(`bugbrief-report-${selected.id}`);
      await refresh();
      setNotice("Report saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function openItem(item: Feedback) {
    if (item.report) {
      setSelected(item);
      setEditorTab("report");
    } else {
      setDraft({
        project_id: item.project_id,
        text: item.text,
        page_url: item.page_url,
        device: item.device,
        browser: item.browser,
      });
      setActiveId(item.id);
      setConsent(false);
      navigate("feedback");
    }
  }
  function share(id?: string) {
    if (!projects.length) {
      setModal("project");
      return;
    }
    setSharing(id || projects[0].id);
  }
  function startFresh() {
    setActiveId(null);
    setDraft({ ...emptyDraft, project_id: projects[0]?.id || "" });
    setConsent(false);
    newFeedback();
  }
  const projectName = (id: string) =>
    projects.find((p) => p.id === id)?.name || "Project";

  return (
    <div className="app-shell">
      {mobileNav && (
        <div className="nav-scrim" onClick={() => setMobileNav(false)} />
      )}
      <aside className={`sidebar ${mobileNav ? "mobile-open" : ""}`}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("overview");
          }}
        >
          <span className="brand-symbol">
            <span>b</span>
            <span className="brand-spark">✳</span>
          </span>
          <span>
            bugbrief<span className="brand-ai">AI</span>
          </span>
        </a>
        <div className="workspace-label">
          <span className="workspace-avatar">W</span>
          <div>
            Company workspace<small>Shared team workspace</small>
          </div>
          <span className="workspace-plan">FREE</span>
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {(
            [
              { id: "overview", label: "Overview", icon: LayoutGrid },
              { id: "feedback", label: "Feedback inbox", icon: Inbox },
              { id: "reports", label: "Bug reports", icon: FileText },
              { id: "projects", label: "Projects", icon: FolderOpen },
            ] as const
          ).map((n) => (
            <button
              key={n.id}
              className={`nav-item ${view === n.id ? "active" : ""}`}
              onClick={() => navigate(n.id)}
            >
              <n.icon size={19} />
              <span>{n.label}</span>
              {n.id === "feedback" && (
                <span className="nav-count">{items.length}</span>
              )}
              {n.id === "reports" && reports.length > 0 && (
                <span className="nav-count">{reports.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-projects">
          <div className="nav-caption">
            YOUR PROJECTS
            <button
              aria-label="Create project"
              onClick={() => setModal("project")}
            >
              <Plus size={15} />
            </button>
          </div>
          {projects.length ? (
            projects.slice(0, 5).map((p, i) => (
              <button
                className={`project-nav ${projectFilter === p.id ? "chosen" : ""}`}
                key={p.id}
                onClick={() => {
                  setProjectFilter(p.id);
                  navigate("feedback");
                }}
              >
                <span className={`project-dot dot-${i % 3}`} />
                <span>{p.name}</span>
              </button>
            ))
          ) : (
            <button
              className="add-first-project"
              onClick={() => setModal("project")}
            >
              <Plus size={14} /> Add your first project
            </button>
          )}
        </div>
        <div className="sidebar-bottom">
          <a className="nav-item" href="/workspace?employee=choose">
            <ArrowRight size={18} />
            <span>Employee accounts</span>
          </a>
          <a className="nav-item" href="/">
            <ArrowRight size={18} />
            <span>Switch role</span>
          </a>
          <div className="small-note">
            <span className="tiny-spark">✳</span>
            <h4>
              Less back-and-forth.
              <br />
              More getting things fixed.
            </h4>
            <p>A little clarity goes a long way.</p>
            <button onClick={() => setModal("guide")}>
              Meet your new workflow <ArrowUpRight size={14} />
            </button>
          </div>
          <button className="nav-item" onClick={() => setModal("settings")}>
            <Settings2 size={18} />
            <span>Settings & usage</span>
          </button>
          <button className="nav-item" onClick={() => setModal("guide")}>
            <CircleHelp size={18} />
            <span>Help & getting started</span>
            <ArrowUpRight size={14} />
          </button>
          <div className="user-row">
            <span className="user-avatar">{userInitial}</span>
            <div className="employee-identity">
              <strong>{employee?.name || "Workspace owner"}</strong>
              <small>{employee?.email || "Local development"}</small>
            </div>
            <span className="online-dot" title="Local workspace" />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobileNav(true)}
            >
              <Menu size={21} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {view === "overview"
                ? "Overview"
                : view === "feedback"
                  ? "Feedback inbox"
                  : view === "reports"
                    ? "Bug reports"
                    : "Projects"}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="local-badge">
              <span /> Local workspace
            </span>
            <button
              className="icon-button"
              aria-label="Open getting started guide"
              onClick={() => setModal("guide")}
            >
              <BookOpen size={18} />
            </button>
            <button
              className="text-button agency-signout"
              onClick={async () => {
                try {
                  await api("/auth/logout", "POST", {});
                  location.assign("/workspace");
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Sign out
            </button>
            <span className="top-divider" />
            <span
              className="user-avatar top-avatar"
              title={employee?.name || "Workspace owner"}
            >
              {userInitial}
            </span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span className="eyebrow-line" /> FROM FEEDBACK TO FIX
              </div>
              <h1>
                {view === "overview"
                  ? "A little feedback. A lot of clarity."
                  : view === "feedback"
                    ? "Make sense of every “it’s broken”."
                    : view === "reports"
                      ? "Clear reports. Confident fixes."
                      : "A home for every project."}
              </h1>
              <p>
                {view === "overview"
                  ? "Turn scattered client feedback into bug reports your team can act on."
                  : view === "feedback"
                    ? "Capture the original feedback. Let AI help with the details."
                    : view === "reports"
                      ? "Review and refine the details before handing them to your team."
                      : "Keep your client feedback and bug reports together."}
              </p>
            </div>
            <button
              className="primary-button heading-action"
              onClick={
                view === "projects" ? () => setModal("project") : startFresh
              }
            >
              <Plus size={17} />
              {view === "projects" ? "New project" : "New feedback"}
            </button>
          </div>
          {error && (
            <div className="alert error" role="alert">
              <CircleHelp size={18} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="toast" role="status">
              <CheckCheck size={18} />
              {notice}
              <button
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {loading && (
            <div className="loading-line">
              <LoaderCircle className="spin" size={15} /> Connecting to your
              workspace…
            </div>
          )}
          {(view === "overview" || view === "projects") && (
            <section className="customer-collection-banner">
              <div>
                <span className="eyebrow">FROM THEIR SCREEN TO YOUR INBOX</span>
                <h2>Stop chasing the details.</h2>
                <p>
                  Give customers a feedback link or a button on their site.
                  Their words, screenshots, browser context and follow-up
                  answers arrive together.
                </p>
                <div className="collection-proof">
                  <span>
                    <Check size={12} />
                    Customer submits directly
                  </span>
                  <span>
                    <Check size={12} />
                    You review the handoff
                  </span>
                </div>
              </div>
              <div className="collection-actions">
                <button className="primary-button" onClick={() => share()}>
                  <Link2 size={16} />
                  Collect customer feedback
                  <ArrowRight size={15} />
                </button>
                <span>
                  {items.filter((item) => item.customer).length} customer
                  submissions received
                </span>
              </div>
            </section>
          )}
          {view === "overview" && (
            <>
              <div className="stats-grid">
                <Stat
                  label="Feedback received"
                  value={items.length}
                  icon={<MessageSquare size={19} />}
                  note="Every detail, in one place"
                />
                <Stat
                  label="Reports generated"
                  value={reports.length}
                  icon={<FileText size={19} />}
                  note="From feedback to a clear brief"
                />
                <Stat
                  label="Open issues"
                  value={
                    items.filter((item) => item.workflow.status !== "resolved")
                      .length
                  }
                  icon={<FileCheck2 size={19} />}
                  note="Still moving toward a resolution"
                />
                <Stat
                  label="Projects"
                  value={projects.length}
                  icon={<Folder size={19} />}
                  note="Organized. In context."
                />
              </div>
            </>
          )}
          {(view === "overview" || view === "feedback") && (
            <details
              className="agency-capture"
              open={view === "feedback" || manualOpen}
              onToggle={(event) => setManualOpen(event.currentTarget.open)}
            >
              <summary>
                <SquarePen size={16} />
                <span>Add feedback on a customer’s behalf</span>
                <span className="manual-intake-tag">MANUAL INTAKE</span>
                <ChevronDown size={15} />
              </summary>
              <div className="work-grid">
                <section className="capture-card">
                  <div className="card-title">
                    <span className="icon-tile coral">
                      <SquarePen size={20} />
                    </span>
                    <div>
                      <h2>Start with what they said.</h2>
                      <p>
                        No perfect brief needed. Just the original feedback.
                      </p>
                    </div>
                    <span className="subtle-tag">
                      {activeFeedback?.customer
                        ? "CUSTOMER SUBMISSION"
                        : "NEW FEEDBACK"}
                    </span>
                  </div>
                  <div className="capture-body">
                    <div className="project-label-row">
                      <label htmlFor="project">
                        Project <span className="required">*</span>
                      </label>
                      <button
                        className="text-button"
                        onClick={() => setModal("project")}
                      >
                        <Plus size={13} /> Create project
                      </button>
                    </div>
                    <div className="select-wrap">
                      <Folder size={16} />
                      <select
                        id="project"
                        disabled={!!activeFeedback?.customer}
                        value={draft.project_id}
                        onChange={(e) => {
                          setDraft({ ...draft, project_id: e.target.value });
                          setActiveId(null);
                        }}
                      >
                        <option value="" disabled>
                          Select a project
                        </option>
                        {projects.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                      <ChevronDown size={15} />
                    </div>
                    <div className="feedback-label-row">
                      <label htmlFor="feedback-text">
                        Client feedback{" "}
                        <span className="optional">or add a screenshot</span>
                      </label>
                      <span>English, हिंदी, or a little of both</span>
                    </div>
                    <div className="textarea-wrap">
                      <textarea
                        ref={composer}
                        id="feedback-text"
                        readOnly={!!activeFeedback?.customer}
                        maxLength={8000}
                        value={draft.text}
                        onChange={(e) =>
                          setDraft({ ...draft, text: e.target.value })
                        }
                        placeholder={
                          "“Checkout pe Pay now click kiya, but nothing happens…”\n\nPaste a message, describe an issue, or tell us what went wrong."
                        }
                      />
                      <div className="textarea-footer">
                        <span>
                          <Globe size={13} /> Write naturally. We’ll bring the
                          structure.
                        </span>
                        <span>
                          {draft.text.length.toLocaleString()} / 8,000
                        </span>
                      </div>
                    </div>
                    <button
                      className="context-toggle"
                      onClick={() => setShowContext(!showContext)}
                      aria-expanded={showContext}
                    >
                      <Link2 size={15} />
                      {showContext
                        ? "Hide additional context"
                        : "Add a page URL, device or browser"}
                      <ChevronDown
                        size={14}
                        className={showContext ? "rotate" : ""}
                      />
                    </button>
                    {showContext && (
                      <div className="context-fields">
                        <label>
                          Page URL
                          <input
                            type="url"
                            placeholder="https://your-project.com/checkout"
                            value={draft.page_url}
                            readOnly={!!activeFeedback?.customer}
                            onChange={(e) =>
                              setDraft({ ...draft, page_url: e.target.value })
                            }
                          />
                        </label>
                        <div className="two-fields">
                          <label>
                            Device
                            <input
                              placeholder="e.g. iPhone 14"
                              maxLength={200}
                              value={draft.device}
                              readOnly={!!activeFeedback?.customer}
                              onChange={(e) =>
                                setDraft({ ...draft, device: e.target.value })
                              }
                            />
                          </label>
                          <label>
                            Browser
                            <input
                              placeholder="e.g. Safari 18"
                              maxLength={200}
                              value={draft.browser}
                              readOnly={!!activeFeedback?.customer}
                              onChange={(e) =>
                                setDraft({ ...draft, browser: e.target.value })
                              }
                            />
                          </label>
                        </div>
                      </div>
                    )}
                    {activeFeedback && (
                      <CustomerContext feedback={activeFeedback} />
                    )}
                    <EvidencePanel
                      feedback={activeFeedback}
                      ensureFeedback={saveDraft}
                      onChange={evidenceUpdated}
                      busy={busy}
                      onBusy={setBusy}
                    />
                    <label className="consent">
                      <input
                        type="checkbox"
                        checked={consent}
                        onChange={(e) => setConsent(e.target.checked)}
                      />
                      <span>
                        I’ve removed sensitive information and agree to send
                        this feedback and saved evidence to Gemini.{" "}
                        <button
                          className="inline-link"
                          onClick={(e) => {
                            e.preventDefault();
                            setModal("settings");
                          }}
                        >
                          Free tier data policy <ArrowUpRight size={11} />
                        </button>
                      </span>
                    </label>
                  </div>
                  {activeFeedback && (
                    <WorkflowPanel
                      key={activeFeedback.id}
                      feedbackId={activeFeedback.id}
                      workflow={activeFeedback.workflow}
                      employees={employees}
                      onChange={(value) =>
                        updateWorkflow(activeFeedback.id, value)
                      }
                    />
                  )}
                  <div className="capture-footer">
                    {activeFeedback ? (
                      <DeleteReportButton
                        disabled={busy}
                        onDelete={() => deleteReport(activeFeedback)}
                      />
                    ) : (
                      <span>
                        <ShieldCheck size={15} /> Your original feedback stays
                        saved.
                      </span>
                    )}
                    <div>
                      <button
                        className="secondary-button"
                        disabled={
                          busy ||
                          (draft.text.trim().length < 3 && !hasSavedEvidence)
                        }
                        onClick={() => submit(false)}
                      >
                        Save draft
                      </button>
                      <button
                        className="primary-button generate-button"
                        disabled={
                          busy ||
                          !consent ||
                          imagesNeedAnalysis ||
                          (draft.text.trim().length < 3 && !hasSavedEvidence)
                        }
                        onClick={() => submit(true)}
                      >
                        {busy ? (
                          <LoaderCircle size={16} className="spin" />
                        ) : (
                          <WandSparkles size={16} />
                        )}{" "}
                        {busy ? "Working…" : "Generate report"}
                        {!busy && <ArrowRight size={15} />}
                      </button>
                    </div>
                  </div>
                </section>
                <aside className="workflow-card">
                  <div className="workflow-top">
                    <span className="outline-spark">
                      <Sparkles size={23} />
                    </span>
                    <span className="mini-pill">A CLEARER WAY TO FIX</span>
                  </div>
                  <h2>
                    From “something’s off”
                    <br />
                    to “here’s the issue”.
                  </h2>
                  <p>
                    A shared understanding, without
                    <br className="desktop-break" /> the endless follow-ups.
                  </p>
                  <div className="workflow-steps">
                    <WorkflowStep
                      number="01"
                      title="Capture the feedback"
                      text="In your client’s words. In their language."
                      icon={<MessageSquare size={15} />}
                      active
                    />
                    <WorkflowStep
                      number="02"
                      title="Connect the details"
                      text="AI separates the knowns from the gaps."
                      icon={<Sparkles size={15} />}
                    />
                    <WorkflowStep
                      number="03"
                      title="Make it ready for a fix"
                      text="Review, edit, and save a clear bug report."
                      icon={<CheckCheck size={15} />}
                    />
                  </div>
                  <div className="workflow-note">
                    <ShieldCheck size={17} />
                    <p>
                      Evidence first. Assumptions never.
                      <br />
                      <span>You always have the final say.</span>
                    </p>
                  </div>
                  <div className="workflow-art" aria-hidden="true">
                    <span className="orbit orbit-one" />
                    <span className="orbit orbit-two" />
                    <span className="art-spark">✳</span>
                  </div>
                </aside>
              </div>
            </details>
          )}
          {view === "projects" ? (
            <section className="projects-grid">
              {projects.map((p, i) => (
                <article className="project-card" key={p.id}>
                  <button
                    className="project-open"
                    onClick={() => {
                      setProjectFilter(p.id);
                      navigate("feedback");
                    }}
                  >
                    <span className={`project-initial initial-${i % 3}`}>
                      {p.name.slice(0, 1).toUpperCase()}
                    </span>
                    <ArrowUpRight className="project-arrow" size={18} />
                    <h2>{p.name}</h2>
                    <p>{p.url || "No project URL added"}</p>
                  </button>
                  <div>
                    <span>
                      {items.filter((f) => f.project_id === p.id).length}{" "}
                      feedback
                    </span>
                    <span>
                      {
                        items.filter((f) => f.project_id === p.id && f.report)
                          .length
                      }{" "}
                      reports
                    </span>
                  </div>
                  <button
                    className="share-project-button"
                    onClick={() => share(p.id)}
                  >
                    <Link2 size={13} />
                    Share feedback link
                    <ArrowUpRight size={13} />
                  </button>
                </article>
              ))}
              <button
                className="project-card new-project-card"
                onClick={() => setModal("project")}
              >
                <Plus size={25} />
                <h2>
                  {projects.length
                    ? "Add a project"
                    : "Create your first project"}
                </h2>
                <p>Give your feedback a place to belong.</p>
              </button>
            </section>
          ) : (
            <section className="recent-section">
              <div className="section-heading">
                <div>
                  <h2>
                    {view === "reports"
                      ? "Your bug reports"
                      : "Recent feedback"}
                    <span className="count-badge">
                      {view === "reports" ? reports.length : items.length}
                    </span>
                  </h2>
                  <p>
                    {view === "reports"
                      ? "AI drafts, shaped by your expertise."
                      : "The latest conversations, with a clear next step."}
                  </p>
                </div>
                {view === "overview" && (
                  <button
                    className="text-button view-all"
                    onClick={() => navigate("feedback")}
                  >
                    View all feedback <ArrowRight size={15} />
                  </button>
                )}
              </div>
              <div className="list-card">
                <div className="list-toolbar">
                  <div className="filter-tabs">
                    <button
                      className={statusFilter === "all" ? "selected" : ""}
                      onClick={() => setStatusFilter("all")}
                    >
                      All {view === "reports" ? "reports" : "feedback"}
                      <span>
                        {view === "reports" ? reports.length : items.length}
                      </span>
                    </button>
                    <button
                      className={statusFilter === "draft" ? "selected" : ""}
                      onClick={() => setStatusFilter("draft")}
                    >
                      Brief drafts
                    </button>
                    <button
                      className={statusFilter === "review" ? "selected" : ""}
                      onClick={() => setStatusFilter("review")}
                    >
                      Briefs in review
                    </button>
                  </div>
                  <div className="list-filters">
                    <div className="search-field">
                      <Search size={15} />
                      <input
                        aria-label="Search feedback"
                        placeholder="Search feedback…"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </div>
                    <select
                      aria-label="Filter by project"
                      value={projectFilter}
                      onChange={(e) => setProjectFilter(e.target.value)}
                    >
                      <option value="all">All projects</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="workflow-filters">
                  <label>
                    Progress
                    <select
                      aria-label="Filter by issue progress"
                      value={progressFilter}
                      onChange={(event) =>
                        setProgressFilter(event.target.value)
                      }
                    >
                      <option value="all">All progress</option>
                      {Object.entries(workflowLabels).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Assigned employee
                    <select
                      aria-label="Filter by assigned employee"
                      value={assigneeFilter}
                      onChange={(event) =>
                        setAssigneeFilter(event.target.value)
                      }
                    >
                      <option value="all">All employees</option>
                      <option value="unassigned">Unassigned</option>
                      {employees.map((employee) => (
                        <option key={employee.id} value={employee.id}>
                          {employee.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="table-header">
                  <span>FEEDBACK / REPORT</span>
                  <span>PROJECT</span>
                  <span>STATUS</span>
                  <span>ADDED</span>
                  <span />
                </div>
                {filtered.length ? (
                  filtered
                    .slice(0, view === "overview" ? 5 : undefined)
                    .map((item) => (
                      <button
                        className="feedback-row"
                        key={item.id}
                        onClick={() => openItem(item)}
                      >
                        <div>
                          <span
                            className={`row-icon ${item.report ? "has-report" : ""}`}
                          >
                            {item.report ? (
                              <FileCheck2 size={17} />
                            ) : (
                              <MessageSquare size={17} />
                            )}
                          </span>
                          <span>
                            <strong>
                              {item.report?.title ||
                                item.text.slice(0, 90) ||
                                item.attachments[0]?.filename ||
                                "Untitled feedback"}
                            </strong>
                            <small>
                              {item.customer && (
                                <span className="customer-source-badge">
                                  Customer ·{" "}
                                </span>
                              )}
                              {item.report
                                ? item.report.category
                                : "Original client feedback"}
                              {item.error && " · AI processing paused"}
                              {" · "}
                              {item.workflow.assigned_to?.name || "Unassigned"}
                            </small>
                          </span>
                        </div>
                        <span className="project-cell">
                          <span className="project-dot" />
                          {projectName(item.project_id)}
                        </span>
                        <span>
                          <WorkflowBadge workflow={item.workflow} />
                        </span>
                        <span className="date-cell">
                          {dateLabel(item.created_at)}
                        </span>
                        <ChevronRight size={16} />
                      </button>
                    ))
                ) : (
                  <div className="empty-state">
                    <div className="empty-icon">
                      <MessageSquare size={24} />
                      <span>
                        <Plus size={10} />
                      </span>
                    </div>
                    <h3>
                      {search ||
                      statusFilter !== "all" ||
                      projectFilter !== "all" ||
                      progressFilter !== "all" ||
                      assigneeFilter !== "all"
                        ? "No matches just yet."
                        : view === "reports"
                          ? "Your first clear brief starts here."
                          : "Good fixes start with a little feedback."}
                    </h3>
                    <p>
                      {search ||
                      statusFilter !== "all" ||
                      projectFilter !== "all" ||
                      progressFilter !== "all" ||
                      assigneeFilter !== "all"
                        ? "Try a different search or filter."
                        : view === "reports"
                          ? "Generate a report from client feedback, then make it your own."
                          : "Add your first client message and turn it into something actionable."}
                    </p>
                    <button
                      className="text-button"
                      onClick={
                        search ||
                        statusFilter !== "all" ||
                        projectFilter !== "all" ||
                        progressFilter !== "all" ||
                        assigneeFilter !== "all"
                          ? () => {
                              setSearch("");
                              setStatusFilter("all");
                              setProjectFilter("all");
                              setProgressFilter("all");
                              setAssigneeFilter("all");
                            }
                          : () => {
                              if (!projects.length) setModal("project");
                              else {
                                newFeedback();
                                if (!draft.text)
                                  setDraft({ ...draft, text: example });
                              }
                            }
                      }
                    >
                      {search ||
                      statusFilter !== "all" ||
                      projectFilter !== "all" ||
                      progressFilter !== "all" ||
                      assigneeFilter !== "all"
                        ? "Clear filters"
                        : projects.length
                          ? "Try with example feedback"
                          : "Create your first project"}
                      <ArrowRight size={14} />
                    </button>
                  </div>
                )}
              </div>
            </section>
          )}
          <footer className="page-footer">
            <span>
              <span className="footer-logo">b✳</span> A little clarity. A
              better handoff.
            </span>
            <button onClick={() => setModal("settings")}>
              <span className={`connection-dot ${ready ? "connected" : ""}`} />
              {!health
                ? "Backend disconnected"
                : ready
                  ? "AI ready · Free tier"
                  : health.usage.paused
                    ? "AI paused · Work saved"
                    : "AI setup needed"}
              <ArrowUpRight size={12} />
            </button>
            <span>Made for the people who build.</span>
          </footer>
        </main>
      </div>
      {sharing && (
        <ShareProject
          projects={projects}
          initialId={sharing}
          close={closeSharing}
        />
      )}
      {modal === "project" && (
        <Modal
          title="Give your project a home."
          subtitle="A project keeps every piece of feedback in context."
          close={closeModal}
        >
          <ProjectForm
            onCreate={async (name, url) => {
              const p = await api<Project>("/projects", "POST", { name, url });
              await refresh();
              setDraft((d) => ({ ...d, project_id: p.id }));
              setModal(null);
              setNotice(`${p.name} is ready. Add your first feedback.`);
            }}
          />
        </Modal>
      )}
      {modal === "settings" && (
        <Modal
          title="A small setup. A clear start."
          subtitle="AI runs through a hosted API. Your key stays on the backend."
          close={closeModal}
        >
          <div className="settings-status">
            <span className={`connection-dot ${ready ? "connected" : ""}`} />
            <strong>
              {ready
                ? "Ready to generate"
                : health?.usage.paused
                  ? "AI processing paused"
                  : "Connect your free API key"}
            </strong>
            <span className="subtle-tag">PHASE 2</span>
          </div>
          <ol className="setup-list">
            <li>
              Create an API key in{" "}
              <a
                href="https://aistudio.google.com/apikey"
                target="_blank"
                rel="noreferrer"
              >
                Google AI Studio <ArrowUpRight size={12} />
              </a>
              . Use a project with billing disabled.
            </li>
            <li>
              Copy <code>backend/.env.example</code> to{" "}
              <code>backend/.env</code>. Set <code>GEMINI_API_KEY</code> and{" "}
              <code>FREE_TIER_CONFIRMED=true</code>.
            </li>
            <li>Restart FastAPI, then refresh this connection.</li>
          </ol>
          <div className="privacy-note">
            <ShieldCheck size={19} />
            <div>
              <strong>Use non-sensitive test feedback.</strong>
              <p>
                Google’s free tier may use input and output to improve products
                and may involve human review. Remove client secrets and personal
                data before processing.{" "}
                <a
                  href="https://ai.google.dev/gemini-api/terms"
                  target="_blank"
                  rel="noreferrer"
                >
                  Read the provider terms ↗
                </a>
              </p>
            </div>
          </div>
          <div className="usage-details">
            <h3>
              Today’s AI activity <span>resets at 00:00 UTC</span>
            </h3>
            <div>
              <span>Requests attempted</span>
              <strong>
                {health?.usage.attempts || 0} / {health?.usage.limit || 20}
              </strong>
            </div>
            <div>
              <span>Reports generated</span>
              <strong>{health?.usage.successful || 0}</strong>
            </div>
            <div>
              <span>Screenshots analyzed</span>
              <strong>{health?.usage.vision_successful || 0}</strong>
            </div>
            <div>
              <span>Input / output tokens</span>
              <strong>
                {health?.usage.input_tokens || 0} /{" "}
                {health?.usage.output_tokens || 0}
              </strong>
            </div>
            <div>
              <span>Average latency</span>
              <strong>
                {health?.usage.average_latency_ms
                  ? `${(health.usage.average_latency_ms / 1000).toFixed(1)}s`
                  : "—"}
              </strong>
            </div>
          </div>
          <p className="fine-print">
            One AI job at a time. No automatic retries or paid fallback. Local
            caps cannot verify or guarantee provider billing limits. Free
            allowance varies by project.
          </p>
          <button
            className="primary-button full-width"
            onClick={() =>
              refresh()
                .then(() => setNotice("Connection refreshed."))
                .catch((e) => setError(e.message))
            }
          >
            Refresh connection <ArrowRight size={16} />
          </button>
        </Modal>
      )}
      {modal === "guide" && (
        <Modal
          title="From message to meaningful."
          subtitle="Your first bug brief, in three small steps."
          close={closeModal}
        >
          <div className="guide-steps">
            <WorkflowStep
              number="01"
              title="Create a project"
              text="Give the client’s website or app a name and a home."
              icon={<Folder size={17} />}
              active
            />
            <WorkflowStep
              number="02"
              title="Keep their original words"
              text="Paste English, Hindi or mixed feedback. Add only the context you actually know."
              icon={<MessageSquare size={17} />}
            />
            <WorkflowStep
              number="03"
              title="Generate, review, refine"
              text="Connect a free API key, generate a real report, and check every claim. Edit before you save."
              icon={<FileCheck2 size={17} />}
            />
          </div>
          <div className="privacy-note">
            <Lightbulb size={20} />
            <p>
              Add a reviewed screenshot, analyze it with your consent, and
              answer clarification questions before revising your report.
              Drafts, screenshots and answers save without provider access.
            </p>
          </div>
          <button
            className="primary-button full-width"
            onClick={() => {
              setModal(null);
              newFeedback();
            }}
          >
            Let’s get started <ArrowRight size={16} />
          </button>
        </Modal>
      )}
      {selected && (
        <div
          className="drawer-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !busy) setSelected(null);
          }}
        >
          <section
            ref={drawerRef}
            className="report-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Review bug report"
            onKeyDown={(e) => {
              if (e.key === "Escape" && !busy) setSelected(null);
            }}
          >
            <div className="drawer-header">
              <span className="eyebrow">
                <FileCheck2 size={16} /> YOUR BUG BRIEF
              </span>
              <button
                className="icon-button"
                aria-label="Close report"
                disabled={busy}
                onClick={() => setSelected(null)}
              >
                <X size={21} />
              </button>
            </div>
            <div className="drawer-title">
              <span className="status-pill review">
                <span />
                In review
              </span>
              <h2>Ready for a human touch.</h2>
              <p>Check the evidence, refine the details, make it yours.</p>
            </div>
            <div className="drawer-tabs">
              <button
                className={editorTab === "report" ? "active" : ""}
                onClick={() => setEditorTab("report")}
              >
                <FileText size={15} /> Bug report
              </button>
              <button
                className={editorTab === "source" ? "active" : ""}
                onClick={() => setEditorTab("source")}
              >
                <MessageSquare size={15} /> Original feedback
              </button>
              <button
                className={editorTab === "evidence" ? "active" : ""}
                onClick={() => setEditorTab("evidence")}
              >
                <ShieldCheck size={15} />
                Evidence & answers
              </button>
            </div>
            <div className="drawer-body">
              {error && (
                <div className="alert error" role="alert">
                  {error}
                </div>
              )}
              <WorkflowPanel
                key={selected.id}
                feedbackId={selected.id}
                workflow={selected.workflow}
                employees={employees}
                onChange={(value) => updateWorkflow(selected.id, value)}
              />
              {selected.proposal && (
                <div className="proposal-banner">
                  <Sparkles size={19} />
                  <div>
                    <strong>A new AI proposal is ready.</strong>
                    <p>
                      Your current edits are preserved. Applying replaces the
                      current report.
                    </p>
                    <details>
                      <summary>Preview new proposal</summary>
                      <pre>{JSON.stringify(selected.proposal, null, 2)}</pre>
                    </details>
                    <button
                      className="secondary-button"
                      disabled={busy}
                      onClick={async () => {
                        try {
                          const f = await api<Feedback>(
                            `/feedback/${selected.id}/apply-proposal`,
                            "POST",
                            { version: selected.version },
                          );
                          setSelected(f);
                          await refresh();
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    >
                      Apply new proposal
                    </button>
                  </div>
                </div>
              )}
              {editorTab === "source" ? (
                <>
                  <span className="eyebrow">ORIGINAL CLIENT FEEDBACK</span>
                  <blockquote>
                    {selected.text ||
                      "No written feedback supplied. See the reviewed screenshots."}
                  </blockquote>
                  <CustomerContext feedback={selected} />
                  <div className="source-details">
                    <p>
                      <strong>Project</strong>
                      {projectName(selected.project_id)}
                    </p>
                    <p>
                      <strong>Page URL</strong>
                      {selected.page_url || "Not supplied"}
                    </p>
                    <p>
                      <strong>Device</strong>
                      {selected.device || "Not supplied"}
                    </p>
                    <p>
                      <strong>Browser</strong>
                      {selected.browser || "Not supplied"}
                    </p>
                    <p>
                      <strong>Submitted</strong>
                      {new Date(selected.created_at).toLocaleString()}
                    </p>
                  </div>
                </>
              ) : editorTab === "evidence" ? (
                <>
                  <CustomerContext feedback={selected} />
                  <EvidencePanel
                    feedback={selected}
                    ensureFeedback={preserveSelectedReport}
                    onChange={evidenceUpdated}
                    busy={busy}
                    onBusy={setBusy}
                    questions={
                      selected.proposal?.questions || editReport?.questions
                    }
                  />
                  <div className="revise-panel">
                    <h3>Bring the new details into your brief.</h3>
                    <p>
                      Your current report and manual edits stay preserved.
                      Review the new proposal before applying it.
                    </p>
                    <label className="consent">
                      <input
                        type="checkbox"
                        checked={consent}
                        onChange={(event) => setConsent(event.target.checked)}
                      />
                      <span>
                        I agree to send saved feedback, clarification answers
                        and screenshot observations to Gemini.
                      </span>
                    </label>
                    <button
                      className="primary-button"
                      disabled={
                        busy ||
                        !consent ||
                        selected.attachments.some((image) => !image.analysis)
                      }
                      onClick={regenerate}
                    >
                      {busy ? (
                        <LoaderCircle size={15} className="spin" />
                      ) : (
                        <Sparkles size={15} />
                      )}
                      Generate revised proposal
                    </button>
                  </div>
                </>
              ) : (
                editReport && (
                  <>
                    <label className="editor-field">
                      Title
                      <input
                        maxLength={180}
                        value={editReport.title}
                        onChange={(e) =>
                          setEditReport({
                            ...editReport,
                            title: e.target.value,
                          })
                        }
                      />
                    </label>
                    <div className="two-fields">
                      <label className="editor-field">
                        Suggested category
                        <select
                          value={editReport.category}
                          onChange={(e) =>
                            setEditReport({
                              ...editReport,
                              category: e.target.value,
                            })
                          }
                        >
                          {[
                            "UI / UX",
                            "Functionality",
                            "Performance",
                            "Content",
                            "Other",
                          ].map((v) => (
                            <option key={v}>{v}</option>
                          ))}
                        </select>
                      </label>
                      <label className="editor-field">
                        Suggested priority
                        <select
                          value={editReport.priority}
                          onChange={(e) =>
                            setEditReport({
                              ...editReport,
                              priority: e.target.value,
                            })
                          }
                        >
                          {["Low", "Medium", "High", "Critical"].map((v) => (
                            <option key={v}>{v}</option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <label className="editor-field">
                      Description
                      <textarea
                        rows={4}
                        maxLength={4000}
                        value={editReport.description}
                        onChange={(e) =>
                          setEditReport({
                            ...editReport,
                            description: e.target.value,
                          })
                        }
                      />
                    </label>
                    <ClaimEditor
                      sources={evidenceLabels}
                      label="Expected behaviour"
                      claim={editReport.expected_behaviour}
                      onChange={(c) =>
                        setEditReport({ ...editReport, expected_behaviour: c })
                      }
                    />
                    <ClaimEditor
                      sources={evidenceLabels}
                      label="Actual behaviour"
                      claim={editReport.actual_behaviour}
                      onChange={(c) =>
                        setEditReport({ ...editReport, actual_behaviour: c })
                      }
                    />
                    {(["reproduction_steps", "observations"] as const).map(
                      (field) => (
                        <div className="editor-field" key={field}>
                          <span>
                            {field === "reproduction_steps"
                              ? "Evidence-backed reproduction steps"
                              : "Observations"}
                          </span>
                          {editReport[field].length === 0 && (
                            <p className="unknown-note">
                              Not established by the submitted evidence.
                            </p>
                          )}
                          {editReport[field].map((c, i) => (
                            <ClaimEditor
                              sources={evidenceLabels}
                              key={i}
                              label={`${i + 1}`}
                              claim={c}
                              onChange={(v) => {
                                const claims = [...editReport[field]];
                                if (v) claims[i] = v;
                                else claims.splice(i, 1);
                                setEditReport({
                                  ...editReport,
                                  [field]: claims,
                                });
                              }}
                            />
                          ))}
                          <button
                            className="text-button"
                            onClick={() =>
                              setEditReport({
                                ...editReport,
                                [field]: [
                                  ...editReport[field],
                                  {
                                    text: "",
                                    evidence_quote: "",
                                    source: "feedback",
                                  },
                                ],
                              })
                            }
                          >
                            <Plus size={12} />
                            Add evidence-backed detail
                          </button>
                        </div>
                      ),
                    )}
                    {(["unknowns", "questions", "hypotheses"] as const).map(
                      (field) => (
                        <label className="editor-field" key={field}>
                          {field === "unknowns"
                            ? "Unknown details"
                            : field === "questions"
                              ? "Suggested clarification questions · answer in Evidence & answers"
                              : "Hypotheses · unverified"}
                          <textarea
                            rows={3}
                            value={editReport[field].join("\n")}
                            onChange={(e) =>
                              setEditReport({
                                ...editReport,
                                [field]: e.target.value
                                  .split("\n")
                                  .filter(Boolean),
                              })
                            }
                          />
                          <small>One item per line. Leave blank if none.</small>
                        </label>
                      ),
                    )}
                    <label className="consent">
                      <input
                        type="checkbox"
                        checked={consent}
                        onChange={(e) => setConsent(e.target.checked)}
                      />
                      <span>
                        I agree to send this non-sensitive feedback to Gemini
                        for regeneration.
                      </span>
                    </label>
                    <button
                      className="text-button"
                      disabled={busy || !consent}
                      onClick={regenerate}
                    >
                      <Sparkles size={15} /> Generate a new proposal
                    </button>
                    <p className="fine-print">
                      Exact source quotations are checked automatically. They do
                      not prove that a claim is correct. Review every factual
                      statement.
                    </p>
                  </>
                )
              )}
            </div>
            <div className="drawer-footer">
              <DeleteReportButton
                disabled={busy}
                onDelete={() => deleteReport(selected)}
              />
              <button
                className="primary-button"
                disabled={busy || !editReport}
                onClick={saveReport}
              >
                {busy ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Check size={16} />
                )}{" "}
                Save report
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
function Stat({
  label,
  value,
  icon,
  note,
}: {
  label: string;
  value: number;
  icon: ReactNode;
  note: string;
}) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <span>{label}</span>
        <span className="stat-icon">{icon}</span>
      </div>
      <strong>{value.toString().padStart(2, "0")}</strong>
      <p>
        <span className="stat-dash" />
        {note}
      </p>
    </div>
  );
}
function WorkflowStep({
  number,
  title,
  text,
  icon,
  active = false,
}: {
  number: string;
  title: string;
  text: string;
  icon: ReactNode;
  active?: boolean;
}) {
  return (
    <div className={`workflow-step ${active ? "current" : ""}`}>
      <span className="step-marker">{icon}</span>
      <div>
        <span className="step-number">{number}</span>
        <h3>{title}</h3>
        <p>{text}</p>
      </div>
    </div>
  );
}
function ProjectForm({
  onCreate,
}: {
  onCreate: (name: string, url: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onCreate(name.trim(), url.trim());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="project-form">
      <label>
        Project name <span className="required">*</span>
        <input
          autoFocus
          required
          maxLength={100}
          placeholder="e.g. Acme storefront"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        Project URL <span className="optional">optional</span>
        <input
          type="url"
          maxLength={2000}
          placeholder="https://acme.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      </label>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <button
        type="submit"
        className="primary-button full-width"
        disabled={busy || !name.trim()}
      >
        {busy ? (
          <LoaderCircle size={16} className="spin" />
        ) : (
          <Plus size={16} />
        )}
        Create project
        <ArrowRight size={16} />
      </button>
    </form>
  );
}
function ClaimEditor({
  sources,
  label,
  claim,
  onChange,
}: {
  sources: Record<string, string>;
  label: string;
  claim: Claim | null;
  onChange: (claim: Claim | null) => void;
}) {
  return (
    <div className="editor-field claim-editor">
      <label>
        {label}
        {claim ? (
          <textarea
            rows={2}
            maxLength={2000}
            value={claim.text}
            onChange={(e) => onChange({ ...claim, text: e.target.value })}
          />
        ) : (
          <span className="unknown-note">Not supplied / unknown</span>
        )}
      </label>
      {claim ? (
        <>
          <details>
            <summary>
              <Link2 size={12} /> Evidence ·{" "}
              {sources[claim.source] || "Removed source · review this claim"}
            </summary>
            <blockquote>
              {claim.evidence_quote || "Add a source quotation below."}
            </blockquote>
            <label>
              Evidence source
              <select
                value={claim.source}
                onChange={(e) =>
                  onChange({
                    ...claim,
                    source: e.target.value as Claim["source"],
                  })
                }
              >
                {Array.from(
                  new Set([...Object.keys(sources), claim.source]),
                ).map((source) => (
                  <option key={source} value={source}>
                    {sources[source] || "Removed source · review required"}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Exact source quotation
              <textarea
                rows={2}
                maxLength={2000}
                value={claim.evidence_quote}
                onChange={(e) =>
                  onChange({ ...claim, evidence_quote: e.target.value })
                }
              />
            </label>
            <small>
              Manually edited claims and quotations require your review.
            </small>
          </details>
          <button
            className="text-button remove-claim"
            onClick={() => onChange(null)}
          >
            Remove detail
          </button>
        </>
      ) : (
        <button
          className="text-button remove-claim"
          onClick={() =>
            onChange({ text: "", evidence_quote: "", source: "feedback" })
          }
        >
          <Plus size={12} /> Add from submitted evidence
        </button>
      )}
    </div>
  );
}
