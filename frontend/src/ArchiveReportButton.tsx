import { useState } from "react";
import { api } from "./types";

export default function ArchiveReportButton({ endpoint, archived, onChange, disabled = false }: {
  endpoint: string; archived: boolean; onChange: (value: any) => void | Promise<void>; disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return <div className="archive-report-control">
    <button type="button" className="secondary-button" disabled={busy || disabled} onClick={async () => {
      setBusy(true); setError("");
      try { const value = await api(endpoint + "/archive", "PATCH", { archived: !archived }); await onChange(value); }
      catch (e) { setError((e as Error).message); } finally { setBusy(false); }
    }}>{busy ? "Saving…" : archived ? "Restore report" : "Archive report"}</button>
    {error && <p className="alert error" role="alert">{error}</p>}
  </div>;
}
