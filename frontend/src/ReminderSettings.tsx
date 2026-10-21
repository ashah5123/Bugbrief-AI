import { useEffect, useState } from "react";
import { api } from "./types";
type Policy = { enabled: boolean; reply_hours: number; retest_hours: number; timezone: string; version: number };

export default function ReminderSettings() {
  const [value, setValue] = useState<Policy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  async function load() {
    setBusy(true);
    try { setValue(await api<Policy>("/team/reminders")); setError(""); setSaved(false); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, []);
  return <section className="conversation-card" aria-label="Automatic reminders">
    <h2>Automatic reminders</h2>
    <p>Send one reminder per waiting period, rather than repeated daily alerts. Checks run while the server is running and catch up after a restart.</p>
    {value && <form onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError(""); setSaved(false);
      try { setValue(await api<Policy>("/team/reminders", "PATCH", value)); setSaved(true); }
      catch (e) { setError((e as Error).message); }
      finally { setBusy(false); }
    }}>
      <fieldset className="permission-controls" disabled={busy}>
        <label className="reminder-toggle"><input type="checkbox" checked={value.enabled} onChange={event => { setSaved(false); setValue({ ...value, enabled: event.target.checked }); }} />Enable automatic reminders</label>
        <label>Hours before reminding the employee to respond<input type="number" min={1} max={720} required value={value.reply_hours} onChange={event => { setSaved(false); setValue({ ...value, reply_hours: Number(event.target.value) }); }} /></label>
        <label>Hours before reminding the customer to retest<input type="number" min={1} max={720} required value={value.retest_hours} onChange={event => { setSaved(false); setValue({ ...value, retest_hours: Number(event.target.value) }); }} /></label>
        <label>Deadline timezone<input required maxLength={100} value={value.timezone} onChange={event => { setSaved(false); setValue({ ...value, timezone: event.target.value }); }} placeholder="e.g. America/Phoenix" /></label>
        <small>Overdue reports alert the owner after the due date ends in this timezone. Unassigned reply reminders also go to the owner. Retest reminders require a customer account; guests keep their private return link. Resolved, unsent and deleted reports are excluded. Archiving does not stop reminders.</small>
        <p>Reminders appear in the notification bell. Email follows each account’s existing email-alert preference; local mode uses the test outbox.</p>
        <button className="primary-button" disabled={busy}>Save reminder settings</button>
      </fieldset>
    </form>}
    {saved && <p role="status">Reminder settings saved</p>}
    {error && <div className="alert error" role="alert">{error}<button type="button" className="text-button" disabled={busy} onClick={() => void load()}>Reload reminder settings</button></div>}
  </section>;
}
