import DuplicateReports from "./DuplicateReports";
import NextStep from "./NextStep";
import TriagePanel from "./TriagePanel";
import Conversation from "./Conversation";
import { useEffect, useRef, useState } from "react";
import { Check, Clock3, LoaderCircle, UserRound } from "lucide-react";
import { api, type IssueWorkflow, type IssueEmployee } from "./types";
export const workflowLabels: Record<string, string> = {
  new: "New",
  needs_information: "Needs information",
  in_progress: "In progress",
  ready_to_retest: "Ready to retest",
  resolved: "Resolved",
};
const transitions: Record<string, string[]> = {
  new: ["needs_information", "in_progress"],
  needs_information: ["new", "in_progress"],
  in_progress: ["needs_information", "ready_to_retest"],
  ready_to_retest: ["needs_information", "in_progress", "resolved"],
  resolved: ["in_progress"],
};
const explanations: Record<string, string> = {
  new: "The company has received your report and will review it.",
  needs_information:
    "The team needs more details. Check the latest update below.",
  in_progress:
    "An assigned employee is investigating or working on this issue.",
  ready_to_retest: "The company says the fix is ready for you to try again.",
  resolved:
    "This issue is resolved. Check the history below for confirmation details.",
};
export function WorkflowBadge({
  workflow,
}: {
  workflow: Pick<IssueWorkflow, "status" | "label">;
}) {
  return (
    <span className={`workflow-badge workflow-${workflow.status}`}>
      <span />
      {workflow.label}
    </span>
  );
}
export function ProgressTimeline({ workflow }: { workflow: IssueWorkflow }) {
  return (
    <div className="progress-timeline">
      <h4>
        <Clock3 size={14} />
        Progress history
      </h4>
      {workflow.history_truncated && (
        <small>Showing the latest 50 updates.</small>
      )}
      <ol>
        {[...(workflow.events || [])].reverse().map((event) => (
          <li key={event.id}>
            <span className="timeline-dot" />
            <div>
              <strong>{event.label}</strong>
              <time dateTime={event.created_at}>
                {new Date(event.created_at).toLocaleString()}
              </time>
              {event.note && <p>{event.note}</p>}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
export function CustomerProgress({
  workflow,
  token,
  onChange,
}: {
  workflow: IssueWorkflow;
  token?: string;
  onChange?: (value: IssueWorkflow) => void;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function confirm(outcome: "works" | "still_happening") {
    setBusy(true);
    setError("");
    try {
      const result = await api<IssueWorkflow>(
        `/public/submissions/${token}/retest`,
        "POST",
        { version: workflow.retest_version, outcome, note },
      );
      onChange?.(result);
      setNote("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="customer-progress-card" aria-label="Report progress">
      <div className="progress-card-heading">
        <span className="eyebrow">YOUR REPORT’S PROGRESS</span>
        <WorkflowBadge workflow={workflow} />
      </div>
      <h2>{workflow.label}</h2>
      <p>{explanations[workflow.status]}</p>
      <NextStep workflow={workflow} audience="customer" />
      <div className="progress-owner">
        <UserRound size={16} />
        <span>
          {workflow.assigned_to
            ? `Assigned to ${workflow.assigned_to.name}`
            : "Waiting for an employee to be assigned"}
        </span>
      </div>
      {token && workflow.status === "ready_to_retest" && (
        <div className="retest-card">
          <h3>Did the fix work?</h3>
          <p>Try the same steps again, then let the team know.</p>
          <label>
            Retest details
            <textarea
              rows={2}
              maxLength={1000}
              value={note}
              disabled={busy}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Required if the issue is still happening"
            />
          </label>
          <div className="retest-actions">
            <button
              className="primary-button"
              disabled={busy}
              onClick={() => void confirm("works")}
            >
              It works
            </button>
            <button
              className="secondary-button"
              disabled={busy || !note.trim()}
              onClick={() => void confirm("still_happening")}
            >
              Still happening
            </button>
          </div>
          <small>
            “It works” resolves your report. “Still happening” sends it back to
            the team.
          </small>
          {error && (
            <p className="alert error" role="alert">
              {error} Refresh this page if the fix has changed.
            </p>
          )}
        </div>
      )}
      <ProgressTimeline workflow={workflow} />
    </section>
  );
}
export default function WorkflowPanel({
  hasCustomer = true,
  feedbackId,
  workflow,
  employees,
  onChange,
}: {
  feedbackId: string;
  hasCustomer?: boolean;
  workflow: IssueWorkflow;
  employees: IssueEmployee[];
  onChange: (value: IssueWorkflow) => void;
}) {
  const [baseVersion, setBaseVersion] = useState(workflow.version);
  const dirty = useRef(false);
  const [status, setStatus] = useState(workflow.status);
  const [employeeId, setEmployeeId] = useState(
    workflow.assigned_employee_id || "",
  );
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (dirty.current && workflow.version !== baseVersion) {
      setError(
        "Progress changed in another tab. Reload progress before saving.",
      );
      return;
    }
    setStatus(workflow.status);
    setEmployeeId(workflow.assigned_employee_id || "");
    setBaseVersion(workflow.version);
  }, [feedbackId, workflow.version]);
  const changed =
    status !== workflow.status ||
    employeeId !== (workflow.assigned_employee_id || "") ||
    !!note.trim();
  return (
    <>
      <NextStep workflow={workflow} audience="company" hasCustomer={hasCustomer} />
      <TriagePanel key={feedbackId} feedbackId={feedbackId} workflow={workflow} onChange={onChange} />
      <section className="workflow-panel" aria-label="Assignment and progress">
        <div className="progress-card-heading">
          <div>
            <span className="eyebrow">FROM REPORT TO RESOLUTION</span>
            <h3>Assignment & progress</h3>
          </div>
          <WorkflowBadge workflow={workflow} />
        </div>
        <p>
          Choose who owns this issue and keep the customer informed. Report
          edits won’t change its progress.
        </p>
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            setBusy(true);
            setError("");
            setSaved(false);
            try {
              const value = await api<IssueWorkflow>(
                `/feedback/${feedbackId}/workflow`,
                "PATCH",
                {
                  version: baseVersion,
                  status,
                  assigned_employee_id: employeeId || null,
                  note,
                },
              );
              dirty.current = false;
              setBaseVersion(value.version);
              onChange(value);
              setNote("");
              setSaved(true);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="workflow-fields">
            <label>
              Assigned employee
              <select
                aria-label="Assigned employee"
                disabled={busy}
                value={employeeId}
                onChange={(event) => {
                  dirty.current = true;
                  setEmployeeId(event.target.value);
                  setSaved(false);
                }}
              >
                <option value="">Unassigned</option>
                {employees.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Issue status
              <select
                aria-label="Issue status"
                disabled={busy}
                value={status}
                onChange={(event) => {
                  dirty.current = true;
                  setStatus(event.target.value);
                  setSaved(false);
                }}
              >
                {[workflow.status, ...transitions[workflow.status]].map(
                  (value) => (
                    <option key={value} value={value}>
                      {workflowLabels[value]}
                    </option>
                  ),
                )}
              </select>
            </label>
          </div>
          {!employees.length && (
            <small>
              Create an employee account to assign work.{" "}
              <a href="/workspace?employee=choose">Employee accounts →</a>
            </small>
          )}
          <label>
            Customer-visible update{" "}
            <span>
              {status === "needs_information" && workflow.status !== status
                ? "required"
                : "optional"}
            </span>
            <textarea
              rows={2}
              maxLength={1000}
              required={
                status === "needs_information" && workflow.status !== status
              }
              disabled={busy}
              value={note}
              onChange={(event) => {
                dirty.current = true;
                setNote(event.target.value);
                setSaved(false);
              }}
              placeholder="e.g. We’re checking checkout. We’ll post an update when it’s ready to try."
            />
          </label>
          <small>
            This update and assignment are visible to the customer. Keep
            internal notes and private details out.
          </small>
          {error && (
            <div className="alert error" role="alert">
              {error}
              <button
                type="button"
                className="text-button"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    const value = await api<IssueWorkflow>(
                      `/feedback/${feedbackId}/workflow`,
                    );
                    dirty.current = !!note.trim();
                    setBaseVersion(value.version);
                    onChange(value);
                    setStatus(value.status);
                    setEmployeeId(value.assigned_employee_id || "");
                    setError("");
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Reload progress
              </button>
            </div>
          )}
          <div className="workflow-actions">
            {saved && (
              <span role="status">
                <Check size={14} />
                Progress saved
              </span>
            )}
            <button className="primary-button" disabled={busy || !changed}>
              {busy ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <Check size={15} />
              )}
              Save progress
            </button>
          </div>
        </form>
        <ProgressTimeline workflow={workflow} />
      </section>
      <DuplicateReports key={`duplicates-${feedbackId}`} feedbackId={feedbackId} employees={employees} onWorkflow={onChange} />
      <Conversation key={feedbackId} feedbackId={feedbackId} />
    </>
  );
}
