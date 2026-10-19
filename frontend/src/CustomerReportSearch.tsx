import { useEffect, useState, type ReactNode } from "react";
import { api } from "./types";
import type { SavedSubmission } from "./customerStorage";
const empty = { q: "", project: "", status: "all", attention: "all" };

export default function CustomerReportSearch({ items, archived, children }: {
  items: SavedSubmission[]; archived: boolean;
  children: (items: SavedSubmission[], filtered: boolean) => ReactNode;
}) {
  const [filters, setFilters] = useState(empty);
  const [result, setResult] = useState<{ key: string; items: SavedSubmission[] } | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const filtered = !!filters.q.trim() || !!filters.project || filters.status !== "all" || filters.attention !== "all";
  const version = JSON.stringify(items);
  const key = JSON.stringify({ ...filters, archive: archived ? "archived" : "active", version });
  useEffect(() => {
    setError("");
    if (!filtered) return;
    let live = true;
    const timer = setTimeout(() => {
      const query = new URLSearchParams({ q: filters.q.trim(), project_id: filters.project, status: filters.status, attention: filters.attention, archive: archived ? "archived" : "active" });
      api<SavedSubmission[]>(`/customer/reports?${query}`).then(items => { if (live) setResult({ key, items }); })
        .catch(e => { if (live) setError(e.message); });
    }, 200);
    return () => { live = false; clearTimeout(timer); };
  }, [key, version, retry]);
  const projects = [...new Map(items.map(item => [item.project_id || item.project_name, item.project_name])).entries()];
  const loading = filtered && result?.key !== key;
  const visible = filtered ? result?.key === key ? result.items : [] : items.filter(item => !!item.archived_at === archived);
  return <section className="customer-report-search" aria-label="Find your reports">
    <form onSubmit={event => event.preventDefault()}>
      <label>Search your reports<input aria-label="Search your reports" type="search" maxLength={200} value={filters.q} placeholder="Description, project or BB-reference" onChange={event => setFilters({ ...filters, q: event.target.value })} /></label>
      <div className="customer-report-filters">
        <label>Project<select aria-label="Filter your reports by project" value={filters.project} onChange={event => setFilters({ ...filters, project: event.target.value })}>
          <option value="">All projects</option>{projects.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select></label>
        <label>Status<select aria-label="Filter your reports by status" value={filters.status} onChange={event => setFilters({ ...filters, status: event.target.value })}>
          <option value="all">All statuses</option><option value="draft">Draft</option><option value="new">New</option><option value="needs_information">Needs information</option><option value="in_progress">In progress</option><option value="ready_to_retest">Ready to retest</option><option value="resolved">Resolved</option>
        </select></label>
        <label>Action needed<select aria-label="Filter your reports by action needed" value={filters.attention} onChange={event => setFilters({ ...filters, attention: event.target.value })}>
          <option value="all">Any action</option><option value="reply">Reply needed</option><option value="retest">Retest requested</option>
        </select></label>
      </div>
      {filtered && <button className="text-button" type="button" onClick={() => { setFilters(empty); setError(""); }}>Reset report filters</button>}
    </form>
    {error ? <div className="alert error" role="alert">{error}<button type="button" className="text-button" onClick={() => setRetry(value => value + 1)}>Retry search</button></div>
      : loading ? <p aria-live="polite">Searching your {archived ? "archived" : "active"} reports…</p>
      : <><p className="customer-search-count" aria-live="polite">{visible.length} {filtered ? "matching " : ""}{archived ? "archived" : "active"} report{visible.length === 1 ? "" : "s"}</p>{children(visible, filtered)}</>}
  </section>;
}
