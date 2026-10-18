import { DuplicateBadge } from "./DuplicateReports";
import { useState } from "react";
import { ArrowRight, CheckCheck, Inbox } from "lucide-react";
import type { Feedback, Project } from "./types";
import NextStep from "./NextStep";
import { WorkflowBadge } from "./WorkflowPanel";
import { compareTriage, overdue, TriageBadges } from "./triage";

export default function MyWork({ employeeId, items, projects, today, open, inbox, resumeDraft }: {
  employeeId: string; items: Feedback[]; projects: Project[]; today: string;
  open: (item: Feedback) => void; inbox: () => void; resumeDraft?: () => void;
}) {
  const [queue, setQueue] = useState("assigned");
  const mine = items.filter(item => item.workflow.assigned_employee_id === employeeId && item.workflow.status !== "resolved");
  const matches = {
    assigned: mine,
    overdue: mine.filter(item => overdue(item.workflow, today)),
    waiting: mine.filter(item => !!item.workflow.waiting_since),
    retest: mine.filter(item => item.workflow.status === "ready_to_retest"),
  };
  const labels = { assigned: "Assigned to me", overdue: "Overdue", waiting: "Customers awaiting reply", retest: "Awaiting retest" };
  const visible = [...matches[queue as keyof typeof matches]].sort((a, b) => compareTriage(a, b, "triage", today));
  return <section className="my-work" aria-label="My work">
    {resumeDraft && <div className="resume-work-draft"><div><strong>You have feedback in progress.</strong><p>Continue the draft you left in this browser.</p></div><button className="secondary-button" onClick={resumeDraft}>Continue your draft <ArrowRight size={15} /></button></div>}
    <div className="my-work-queues" aria-label="My work queues">
      {Object.entries(labels).map(([value, label]) => <button key={value} aria-pressed={queue === value} onClick={() => setQueue(value)}>
        <strong>{matches[value as keyof typeof matches].length}</strong><span>{label}</span>
      </button>)}
    </div>
    <div className="section-heading"><div><h2>{labels[queue as keyof typeof labels]}</h2><p>Only your assigned, unresolved reports. Your project inbox also includes work the team hasn’t assigned.</p></div></div>
    {visible.length ? <div className="my-work-list">{visible.map(item => <button className="my-work-item" data-work-report-id={item.id} key={item.id} onClick={() => open(item)}>
      <div className="my-work-item-heading"><strong>{item.report?.title || item.text.slice(0, 110) || "Untitled feedback"}</strong><WorkflowBadge workflow={item.workflow} /></div>
      <span className="my-work-project">{projects.find(project => project.id === item.project_id)?.name || "Project"}{item.customer?.reporter_name ? ` · ${item.customer.reporter_name}` : ""}</span>
      <DuplicateBadge value={item.duplicate_group} />
      <TriageBadges workflow={item.workflow} today={today} />
      <NextStep workflow={item.workflow} audience="company" hasCustomer={!!item.customer} compact />
      <span className="work-open">Open report <ArrowRight size={14} /></span>
    </button>)}</div> : <div className="customer-empty">
      {queue === "assigned" ? <Inbox size={26} /> : <CheckCheck size={26} />}
      <h3>{queue === "assigned" ? "No open reports assigned to you." : "Nothing in this queue."}</h3>
      <p>{queue === "assigned" ? "Ask your team to assign a report, or review the reports in your projects." : "Switch queues to see your other work."}</p>
      <button className="secondary-button" onClick={inbox}>Open project inbox <ArrowRight size={15} /></button>
    </div>}
  </section>;
}
