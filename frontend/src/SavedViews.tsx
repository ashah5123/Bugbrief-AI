import { useEffect, useState } from "react";
import { api } from "./types";
import type { QueueFilters } from "./queueFilters";
type SavedView = { id: string; name: string; filters: QueueFilters; version: number; unavailable: boolean };

export default function SavedViews({ filters, apply }: { filters: QueueFilters; apply: (filters: QueueFilters) => void }) {
  const [rows, setRows] = useState<SavedView[]>([]);
  const [selected, setSelected] = useState<SavedView | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => {
    let live = true;
    const load = () => api<SavedView[]>("/saved-views").then(value => { if (live) { setRows(value); setLoading(false); } }).catch(e => { if (live) { setError(e.message); setLoading(false); } });
    void load();
    window.addEventListener("focus", load);
    const timer = window.setInterval(load, 15000);
    return () => { live = false; window.removeEventListener("focus", load); clearInterval(timer); };
  }, []);
  async function act(operation: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await operation(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  function select(value: SavedView | null) { setSelected(value); setName(value?.name || ""); setConfirmDelete(false); }
  async function save(update = false) {
    await act(async () => {
      const value = await api<SavedView>(`/saved-views${update && selected ? `/${selected.id}` : ""}`, update ? "PATCH" : "POST", { name, filters, ...(update && selected ? { version: selected.version } : {}) });
      select(value); setRows(current => [...current.filter(row => row.id !== value.id), value].sort((a, b) => a.name.localeCompare(b.name)));
      setNotice(update ? "Saved view updated" : "View saved to your account");
    });
  }
  const unavailable = selected && (rows.find(row => row.id === selected.id)?.unavailable ?? selected.unavailable);
  return <section className="saved-views" aria-label="Saved views">
    <h3>Saved views</h3><p>Personal shortcuts, available across browsers.</p>
    <fieldset className="permission-controls" disabled={busy || loading}>
      <div className="saved-view-open"><label>Saved view<select aria-label="Saved view" value={selected?.id || ""} onChange={event => select(rows.find(row => row.id === event.target.value) || null)}>
        <option value="">Choose a saved view</option>{rows.map(row => <option key={row.id} value={row.id}>{row.name}{row.unavailable ? " · Unavailable" : ""}</option>)}
      </select></label><button type="button" className="secondary-button" disabled={!selected || !!unavailable} onClick={() => void act(async () => {
        const value = await api<SavedView>(`/saved-views/${selected!.id}`);
        select(value); setRows(current => current.map(row => row.id === value.id ? value : row));
        if (value.unavailable) throw new Error("This view uses a project, employee or customer no longer available. Choose accessible filters and update the view.");
        apply(value.filters); setNotice(`Opened ${value.name}`);
      })}>Open view</button></div>
      {unavailable && <p className="permission-notice">This view uses a project, employee or customer no longer available. Choose accessible inbox filters and update it, or delete it.</p>}
      <details className="saved-view-management"><summary>Manage saved views</summary>
      <form className="saved-view-save" onSubmit={event => { event.preventDefault(); void save(); }}>
        <label>View name<input aria-label="View name" required maxLength={80} value={name} onChange={event => setName(event.target.value)} placeholder="e.g. My urgent reports" /></label>
        <button className="secondary-button" disabled={!name.trim() || filters.search.length > 200}>Save as new view</button>
        {selected && <button type="button" className="secondary-button" disabled={!name.trim() || filters.search.length > 200} onClick={() => void save(true)}>Update saved view</button>}
      </form>
      <small>Keep up to 20 views. Saves current filters, search, sorting and active/archive scope. Updating replaces the selected view with your current filters.</small>
      {filters.search.length > 200 && <p role="alert">Shorten the search to 200 characters before saving.</p>}
      {selected && (!confirmDelete ? <button type="button" className="text-button" onClick={() => setConfirmDelete(true)}>Delete saved view</button> : <div className="saved-view-delete"><p>Delete “{selected.name}”? Reports are kept.</p><button type="button" className="secondary-button" onClick={() => setConfirmDelete(false)}>Keep view</button><button type="button" className="secondary-button" onClick={() => void act(async () => {
        await api(`/saved-views/${selected.id}`, "DELETE", { version: selected.version });
        setRows(current => current.filter(row => row.id !== selected.id)); select(null); setNotice("Saved view deleted");
      })}>Confirm delete view</button></div>)}
      </details>
    </fieldset>
    {notice && <p role="status">{notice}</p>}
    {error && <div role="alert" className="alert error">{error}<button type="button" className="text-button" disabled={busy} onClick={() => void act(async () => {
      setRows(await api<SavedView[]>("/saved-views")); select(null); setLoading(false);
    })}>Reload saved views</button></div>}
  </section>;
}
