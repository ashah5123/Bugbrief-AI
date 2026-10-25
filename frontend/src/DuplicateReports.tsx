import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Feedback, type IssueEmployee, type IssueWorkflow } from "./types";
import { WorkflowBadge, workflowLabels } from "./WorkflowPanel";
import { FixFields, emptyFix, completeFix } from "./FixDetails";
import { useUnsavedChanges } from "./unsavedChanges";

type Member = { id: string; reference: string; title: string; workflow: IssueWorkflow };
type Group = { main_feedback_id: string; version: number; work_status: string; assigned_employee_id: string | null; members: Member[] };
type Result = { group: Group | null; updated_count?: number };
type Candidate = { id: string; reference: string; title: string; version: number };

export function DuplicateBadge({ value }: { value: Feedback["duplicate_group"] }) {
  return value ? <span className="duplicate-badge">{value.is_main ? `Shared issue · ${value.count} reports` : "Linked duplicate"}</span> : null;
}

export default function DuplicateReports({ feedbackId, employees, onWorkflow }: {
  feedbackId: string; employees: IssueEmployee[]; onWorkflow: (value: IssueWorkflow) => void;
}) {
  const [data, setData] = useState<Result | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [note, setNote] = useState("");
  const [fix, setFix] = useState(emptyFix);
  const [savedFix, setSavedFix] = useState(emptyFix);
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const ownerEdited = useRef(false);
  const pending = useRef<{ signature: string; id: string; payload: Record<string, unknown> } | null>(null);
  const group = data?.group;
  const isMain = group?.main_feedback_id === feedbackId;
  useUnsavedChanges(`report:${feedbackId}`, "shared update or retest instructions", !!isMain && (!!note.trim() || !!body.trim() || JSON.stringify(fix) !== JSON.stringify(savedFix) || (ownerEdited.current && employeeId !== (group?.assigned_employee_id || ""))), busy);
  const root = group?.members.find(member => member.id === group.main_feedback_id);
  const openCount = group?.members.filter(member => member.workflow.status !== "resolved").length || 0;
  async function load() {
    const value = await api<Result>(`/feedback/${feedbackId}/duplicates`);
    setData(value);
    return value;
  }
  useEffect(() => {
    let live = true;
    const refresh = () => api<Result>(`/feedback/${feedbackId}/duplicates`).then(value => {
      if (!live) return;
      setData(value);
      if (!ownerEdited.current) setEmployeeId(value.group?.assigned_employee_id || "");
    }).catch(e => { if (live) setError(e.message); });
    void refresh();
    const timer = window.setInterval(refresh, 15000);
    window.addEventListener("focus", refresh);
    return () => { live = false; clearInterval(timer); window.removeEventListener("focus", refresh); };
  }, [feedbackId]);
  useEffect(() => {
    if (!data || group) return;
    let live = true;
    setCandidatesLoading(true); setSelected(""); setCandidates([]);
    const timer = setTimeout(() => {
      api<Candidate[]>(`/feedback/${feedbackId}/duplicates/candidates?q=${encodeURIComponent(search)}`)
        .then(value => { if (live) { setCandidates(value); setCandidatesLoading(false); } })
        .catch(e => { if (live) { setError(e.message); setCandidatesLoading(false); } });
    }, 200);
    return () => { live = false; clearTimeout(timer); };
  }, [feedbackId, search, !!data, !!group, reloadKey]);
  async function mutate(path: string, method: string, payload: unknown) {
    setBusy(true); setError(""); setNotice("");
    try {
      const value = await api<Result>(`/feedback/${feedbackId}/duplicates${path}`, method, payload);
      if (!value.group) { setCandidatesLoading(true); setSelected(""); }
      setData(value);
      void api<IssueWorkflow>(`/feedback/${feedbackId}/workflow`).then(onWorkflow).catch(() => {});
      // Refresh list badges and other affected report snapshots through the normal authorized refresh.
      window.dispatchEvent(new Event("bugbrief-reports-updated"));
      return value;
    } catch (e) {
      if (e instanceof ApiError && e.status < 500) pending.current = null;
      setError((e as Error).message); return null;
    }
    finally { setBusy(false); }
  }
  async function sharedAction(path: string, payload: Record<string, unknown>) {
    const signature = JSON.stringify({ path, ...payload, version: undefined, report_versions: undefined });
    if (pending.current?.signature !== signature) pending.current = { signature, id: crypto.randomUUID(), payload };
    const value = await mutate(path, "POST", { ...pending.current.payload, request_id: pending.current.id });
    if (value) pending.current = null;
    return value;
  }
  return <section className="duplicate-panel workflow-panel" aria-label="Linked reports">
    <span className="eyebrow">ONE FIX, SEPARATE CUSTOMER REPORTS</span>
    <h3>Linked reports</h3>
    <p>Link reports about the same bug within this project. Conversations stay private to each customer. Linking does not copy evidence or change progress.</p>
    {!data && !error && <p>Loading linked reports…</p>}
    {data && !group && <form onSubmit={async event => {
      event.preventDefault();
      const main = candidates.find(candidate => candidate.id === selected);
      if (!main) return;
      const value = await mutate("", "POST", { main_feedback_id: main.id, version: main.version });
      if (value) setNotice("Report linked. Manage the shared fix from the main report.");
    }}>
      <label>Find the main report
        <input aria-label="Find the main report" type="search" maxLength={120} value={search} disabled={busy} onChange={event => { setCandidatesLoading(true); setSelected(""); setSearch(event.target.value); }} placeholder="Search title, feedback or report ID" />
      </label>
      <label>Main report
        <select aria-label="Main report" value={selected} disabled={busy || candidatesLoading} onChange={event => setSelected(event.target.value)}>
          <option value="">Choose a report in this project</option>
          {candidates.map(candidate => <option key={candidate.id} value={candidate.id}>BB-{candidate.reference} · {candidate.title}</option>)}
        </select>
      </label>
      <small>Showing up to 50 matches. Search to find an older report. Reports already linked as duplicates cannot be selected as a main report.</small>
      <button className="secondary-button" disabled={busy || candidatesLoading || !selected}>Link as duplicate</button>
    </form>}
    {group && <>
      <div className="shared-issue-heading"><strong>{group.members.length} linked reports</strong><span>Shared fix: {openCount ? workflowLabels[group.work_status] : "All reports resolved"}</span></div>
      {!isMain && <p>Manage the shared fix on <a href={`/workspace?report=${group.main_feedback_id}`}>the main report: {root?.title || "Open main report"}</a>. Individual progress changes apply only to this report.</p>}
      <ul className="duplicate-members">{group.members.map(member => <li key={member.id}>
        <div><a href={`/workspace?report=${member.id}`}>{member.title}</a><small>BB-{member.reference}{member.id === group.main_feedback_id ? " · Main report" : ""}</small></div>
        <WorkflowBadge workflow={member.workflow} />
      </li>)}</ul>
      <small>{group.members.filter(member => member.workflow.status === "resolved").length} resolved · {openCount} still open. Each customer confirms their own fix.</small>
      {isMain && <>
        <form className="shared-work-form" onSubmit={event => event.preventDefault()}>
          <h4>Manage the shared fix</h4>
          <p>Assignment and updates below apply to {openCount} open reports. Resolved reports stay resolved. Each report keeps its own priority and due date.</p>
          <label>Shared fix owner
            <select aria-label="Shared fix owner" value={employeeId} disabled={busy} onChange={event => { ownerEdited.current = true; setEmployeeId(event.target.value); }}>
              <option value="">Choose an employee</option>
              {employees.map(employee => <option key={employee.id} value={employee.id}>{employee.name}</option>)}
            </select>
          </label>
          <label>Shared customer update
            <textarea aria-label="Shared customer update" maxLength={1000} rows={3} value={note} disabled={busy} onChange={event => setNote(event.target.value)} placeholder="What are you working on? For a retest, explain what changed and the steps to try." />
          </label>
          <small>This text is public on every affected open report. Keep customer names and private details out.</small>
          <FixFields value={fix} disabled={busy} prefix="Shared: " onChange={setFix} />
          <small>All three fix details are required for a shared retest. Each affected customer receives the same instructions.</small>
          <div className="shared-work-actions">
            {([['in_progress', 'Start shared work'], ['ready_to_retest', 'Request shared retest']] as const).map(([status, label]) => <button key={status} type="button" className="secondary-button"
              disabled={busy || !employeeId || !note.trim() || !openCount || (status === 'ready_to_retest' && (!completeFix(fix) || (!['in_progress','ready_to_retest'].includes(group.work_status) && !['in_progress','ready_to_retest'].includes(root?.workflow.status || ''))))}
              onClick={async () => {
                const value = await sharedAction("/workflow", { version: group.version, report_versions: Object.fromEntries(group.members.map(member => [member.id, member.workflow.version])), status, assigned_employee_id: employeeId, note, ...(status === 'ready_to_retest' ? { fix_details: fix } : {}) });
                if (value) { ownerEdited.current = false; if (status === 'ready_to_retest') setSavedFix(fix); setNotice(`Updated ${value.updated_count} open reports.${status === 'ready_to_retest' ? ' Customers can now test independently.' : ''}`); setNote(""); }
              }}>{label}</button>)}
          </div>
        </form>
        <form className="shared-message-form" onSubmit={async event => {
          event.preventDefault();
          const value = await sharedAction("/updates", { version: group.version, body });
          if (value) { setNotice(`Update posted separately to ${value.updated_count} reports.`); setBody(""); }
        }}>
          <h4>Send an update to every linked report</h4>
          <label>Update for all linked reports
            <textarea aria-label="Update for all linked reports" rows={3} required maxLength={4000} value={body} disabled={busy} onChange={event => setBody(event.target.value)} />
          </label>
          <small>This includes resolved reports and does not change status. Only this new message is shared; existing conversations are never copied.</small>
          <button className="primary-button" disabled={busy || !body.trim()}>Send update to {group.members.length} reports</button>
        </form>
      </>}
      {!confirmUnlink ? <button className="text-button" disabled={busy} onClick={() => setConfirmUnlink(true)}>{isMain ? "Unlink all reports" : "Unlink this report"}</button> : <div className="unlink-confirm">
        <p>{isMain ? "Unlink every report in this group?" : "Unlink this report from the shared issue?"} Messages, assignments and retest results stay on their individual reports.</p>
        <button className="secondary-button" disabled={busy} onClick={() => setConfirmUnlink(false)}>Keep linked</button>
        <button className="secondary-button" disabled={busy} onClick={async () => {
          const value = await mutate("", "DELETE", { version: group.version });
          if (value) { setConfirmUnlink(false); setNotice("Reports unlinked. Individual reports are preserved."); }
        }}>Confirm unlink</button>
      </div>}
    </>}
    {notice && <p className="shared-notice" role="status">{notice}</p>}
    {error && <div className="alert error" role="alert">{error}
      <button type="button" className="text-button" disabled={busy} onClick={async () => {
        setBusy(true); setCandidatesLoading(true); setSelected("");
        try { await load(); setReloadKey(value => value + 1); setError(""); } catch (e) { setError((e as Error).message); }
        finally { setBusy(false); }
      }}>Reload linked reports</button>
    </div>}
  </section>;
}
