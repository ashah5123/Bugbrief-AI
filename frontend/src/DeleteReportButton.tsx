import { useEffect, useId, useRef, useState } from "react";
import { LoaderCircle, Trash2 } from "lucide-react";
export default function DeleteReportButton({
  onDelete,
  disabled = false,
  customer = false,
}: {
  onDelete: () => Promise<void>;
  disabled?: boolean;
  customer?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);
  return (
    <>
      <button
        type="button"
        className="delete-report-button"
        disabled={disabled}
        onClick={() => {
          setError("");
          setOpen(true);
        }}
      >
        <Trash2 size={15} />
        {customer ? "Delete my report" : "Delete report"}
      </button>
      <dialog
        className="delete-dialog"
        ref={dialog}
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        onCancel={(event) => {
          if (busy) event.preventDefault();
          else setOpen(false);
        }}
      >
        <span className="delete-dialog-icon">
          <Trash2 size={23} />
        </span>
        <h2 id={titleId}>
          {customer ? "Delete your report?" : "Delete this report?"}
        </h2>
        <p id={descriptionId}>
          This permanently removes the report, original feedback, screenshots
          and answers from the workspace. You cannot undo this.
        </p>
        {error && (
          <p className="alert error" role="alert">
            {error}
          </p>
        )}
        <div className="delete-dialog-actions">
          <button
            type="button"
            className="secondary-button"
            autoFocus
            disabled={busy}
            onClick={() => setOpen(false)}
          >
            Keep report
          </button>
          <button
            type="button"
            className="danger-button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                await onDelete();
                setOpen(false);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <Trash2 size={15} />
            )}
            Delete permanently
          </button>
        </div>
      </dialog>
    </>
  );
}
