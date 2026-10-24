import { ArrowRight } from "lucide-react";
import type { Feedback, Project } from "./types";
import { needsAttention } from "./queueFilters";

export const healthMetrics = [['open', 'Open reports'], ['overdue', 'Overdue work'], ['waiting', 'Customers awaiting reply'], ['retest', 'Awaiting retest'], ['unassigned', 'Unassigned reports']] as const;
export function ProjectHealthCounts({ project, items, today, open }: { project: Project; items: Feedback[]; today: string; open: (projectId: string, attention: string) => void }) {
  const active = items.filter(item => item.project_id === project.id && !item.archived_at);
  return <div className="project-health-counts" role="group" aria-label={`Health for ${project.name}`}>
    {healthMetrics.map(([key, label]) => <button type="button" key={key} onClick={() => open(project.id, key)}>
      <strong>{active.filter(item => needsAttention(item, key, today)).length}</strong><span>{label}</span><ArrowRight size={13} />
    </button>)}
    <small>{!active.length ? "No active reports." : !active.some(item => item.workflow.status !== 'resolved') ? "No open reports." : "Active reports only. Counts can overlap."}</small>
  </div>;
}

export default function ProjectHealth({ projects, items, today, updatedAt, open }: { projects: Project[]; items: Feedback[]; today: string; updatedAt: string; open: (projectId: string, attention: string) => void }) {
  return <section className="project-health" aria-label="Project health overview">
    <div className="section-heading"><div><h2>Project health</h2><p>See where help is needed. Open a count to see its reports.</p></div></div>
    <p className="muted">Last refreshed <time dateTime={updatedAt}>{new Date(updatedAt).toLocaleTimeString()}</time></p>
    {projects.length ? <div className="project-health-grid">{projects.map(project => <article className="project-health-card" key={project.id}>
      <h3>{project.name}</h3><ProjectHealthCounts project={project} items={items} today={today} open={open} />
    </article>)}</div> : <p>Create a project to see its report queues here.</p>}
  </section>;
}
