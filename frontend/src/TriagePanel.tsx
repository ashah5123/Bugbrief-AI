import { useEffect, useRef, useState } from "react";
import { api, type IssuePriority, type IssueWorkflow } from "./types";
import { priorityLabels, TriageBadges, todayLocal } from "./triage";
import { useUnsavedChanges } from "./unsavedChanges";

export default function TriagePanel({ feedbackId, workflow, onChange }: {
  feedbackId: string; workflow: IssueWorkflow; onChange: (value: IssueWorkflow) => void;
}) {
  const [priority, setPriority] = useState<IssuePriority>(workflow.priority || "normal");
  const [due, setDue] = useState(workflow.due_date || "");
  const [version, setVersion] = useState(workflow.version);
  const dirty = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  function adopt(value: IssueWorkflow) {
    setPriority(value.priority || "normal");
    setDue(value.due_date || "");
    setVersion(value.version);
  }
  useEffect(() => {
    if (dirty.current && workflow.version !== version) {
      setError("Report changed in another tab. Reload triage before saving.");
      return;
    }
    adopt(workflow);
  }, [feedbackId, workflow.version]);
  const changed = priority !== (workflow.priority || "normal") || due !== (workflow.due_date || "");
  useUnsavedChanges(`report:${feedbackId}`, "priority or deadline changes", changed, busy);
  return <section className="workflow-panel triage-panel" aria-label="Report priority and deadline">
    <span className="eyebrow">PLAN THE WORK</span>
    <h3>Priority & deadline</h3>
    <p>Company-only planning. Due dates are calendar dates, shown in your local timezone.</p>
    <TriageBadges workflow={workflow} today={todayLocal()} />
    <form onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError(""); setSaved(false);
      try {
        const value = await api<IssueWorkflow>(`/feedback/${feedbackId}/triage`, "PATCH", {
          version, priority, due_date: due || null,
        });
        dirty.current = false; adopt(value); onChange(value); setSaved(true);
      } catch (e) { setError((e as Error).message); }
      finally { setBusy(false); }
    }}>
      <div className="workflow-fields">
        <label>Report priority
          <select aria-label="Report priority" value={priority} disabled={busy} onChange={event => {
            dirty.current = true; setPriority(event.target.value as IssuePriority); setSaved(false);
          }}>
            {Object.entries(priorityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>Due date <span>optional</span>
          <input aria-label="Due date" type="date" value={due} disabled={busy} max="9999-12-31" onChange={event => {
            dirty.current = true; setDue(event.target.value); setSaved(false);
          }} />
        </label>
      </div>
      {due && <button type="button" className="text-button" disabled={busy} onClick={() => {
        dirty.current = true; setDue(""); setSaved(false);
      }}>Remove due date</button>}
      {error && <div className="alert error" role="alert">{error}
        <button type="button" className="text-button" disabled={busy} onClick={async () => {
          setBusy(true);
          try {
            const value = await api<IssueWorkflow>(`/feedback/${feedbackId}/workflow`);
            dirty.current = false; adopt(value); onChange(value); setError(""); setSaved(false);
          } catch (e) { setError((e as Error).message); }
          finally { setBusy(false); }
        }}>Reload triage</button>
      </div>}
      <div className="workflow-actions">
        {saved && <span role="status">Triage saved</span>}
        <button className="primary-button" disabled={busy || !changed}>{busy ? "Saving…" : "Save triage"}</button>
      </div>
    </form>
  </section>;
}
