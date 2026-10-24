import type { Feedback, Project } from "./types";
import { customerKey, overdue } from "./triage";

export type QueueFilters = {
  view: "feedback" | "reports"; archive: boolean; search: string; project_id: string;
  status: string; progress: string; priority: string; attention: string;
  assignee: string; customer: string; sort: string;
};
export const defaultFilters: QueueFilters = { view: "feedback", archive: false, search: "", project_id: "all", status: "all", progress: "all", priority: "all", attention: "all", assignee: "all", customer: "all", sort: "triage" };
export function needsAttention(item: Feedback, attention: string, today: string) {
  const open = item.workflow.status !== "resolved";
  return attention === "all" ||
    (attention === "open" && open) ||
    (attention === "overdue" && overdue(item.workflow, today)) ||
    (attention === "waiting" && open && !!item.workflow.waiting_since) ||
    (attention === "today" && open && item.workflow.due_date === today) ||
    (attention === "retest" && item.workflow.status === "ready_to_retest") ||
    (attention === "unassigned" && open && !item.workflow.assigned_employee_id);
}
export function matchesQueue(item: Feedback, filters: QueueFilters, today: string, projects: Project[], employeeId?: string) {
  const assignee = filters.assignee === "me" ? employeeId || "unavailable" : filters.assignee;
  return !!item.archived_at === filters.archive && (filters.view !== "reports" || !!item.report) &&
    (filters.project_id === "all" || item.project_id === filters.project_id) &&
    (filters.status === "all" || item.status === filters.status) &&
    (filters.progress === "all" || item.workflow.status === filters.progress) &&
    (filters.priority === "all" || (item.workflow.priority || "normal") === filters.priority) &&
    (filters.customer === "all" || customerKey(item) === filters.customer) &&
    needsAttention(item, filters.attention, today) &&
    (assignee === "all" || (assignee === "unassigned" ? !item.workflow.assigned_employee_id : item.workflow.assigned_employee_id === assignee)) &&
    `${item.id} BB-${item.id.slice(0, 8)} ${item.text} ${item.report?.title || ""} ${item.customer?.reporter_name || ""} ${item.workflow.assigned_to?.name || ""} ${projects.find(project => project.id === item.project_id)?.name || ""}`.toLowerCase().includes(filters.search.trim().toLowerCase());
}
