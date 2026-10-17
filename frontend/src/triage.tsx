import type { Feedback, IssuePriority, IssueWorkflow } from "./types";

export const priorityLabels: Record<IssuePriority, string> = {
  urgent: "Urgent", high: "High", normal: "Normal", low: "Low",
};
export function todayLocal() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export function overdue(workflow: IssueWorkflow, today: string) {
  return workflow.status !== "resolved" && !!workflow.due_date && workflow.due_date < today;
}
export function dueLabel(value: string) {
  // Calendar dates stay in the employee's timezone; parsing as UTC shifts the day.
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(0);
  date.setFullYear(year, month - 1, day);
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
const rank: Record<IssuePriority, number> = { urgent: 0, high: 1, normal: 2, low: 3 };
export function compareTriage(a: Feedback, b: Feedback, sort: string, today: string) {
  if (sort === "newest") return b.created_at.localeCompare(a.created_at) || a.id.localeCompare(b.id);
  if (sort === "due") return (a.workflow.due_date || "9999-99-99").localeCompare(b.workflow.due_date || "9999-99-99") || b.created_at.localeCompare(a.created_at) || a.id.localeCompare(b.id);
  return Number(a.workflow.status === "resolved") - Number(b.workflow.status === "resolved") ||
    Number(overdue(b.workflow, today)) - Number(overdue(a.workflow, today)) ||
    rank[a.workflow.priority || "normal"] - rank[b.workflow.priority || "normal"] ||
    Number(!!b.workflow.waiting_since) - Number(!!a.workflow.waiting_since) ||
    (a.workflow.due_date || "9999-99-99").localeCompare(b.workflow.due_date || "9999-99-99") ||
    b.created_at.localeCompare(a.created_at) || a.id.localeCompare(b.id);
}
export function customerKey(item: Feedback) {
  return item.customer ? `customer:${item.customer.id}` : "manual";
}
export function TriageBadges({ workflow, today }: { workflow: IssueWorkflow; today: string }) {
  return <span className="triage-badges">
    <span className={`priority-badge priority-${workflow.priority || "normal"}`}>{priorityLabels[workflow.priority || "normal"]}</span>
    {workflow.due_date && <span className={overdue(workflow, today) ? "deadline overdue" : "deadline"}>
      {overdue(workflow, today) ? "Overdue · " : "Due "}{dueLabel(workflow.due_date)}
    </span>}
    {workflow.waiting_since && <span className="waiting-badge" title={`Waiting since ${new Date(workflow.waiting_since).toLocaleString()}`}>Customer awaiting reply</span>}
  </span>;
}
