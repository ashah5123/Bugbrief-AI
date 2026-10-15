import { useEffect, useRef, useState, type PointerEvent } from "react";
import {
  Check,
  Eraser,
  ImagePlus,
  RotateCcw,
  ShieldCheck,
  Undo2,
  X,
} from "lucide-react";

export const MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024;
type Rect = { x: number; y: number; width: number; height: number };
export default function ScreenshotReview({
  busy,
  onSave,
  onError,
}: {
  busy: boolean;
  onSave: (blob: Blob, name: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const image = useRef<HTMLImageElement | null>(null);
  const imageUrl = useRef("");
  const [file, setFile] = useState<File | null>(null);
  const [rects, setRects] = useState<Rect[]>([]);
  const [start, setStart] = useState<{ x: number; y: number } | null>(null);
  const [selection, setSelection] = useState<Rect | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [manual, setManual] = useState<Rect>({
    x: 0,
    y: 0,
    width: 100,
    height: 40,
  });
  const [saving, setSaving] = useState(false);
  useEffect(
    () => () => {
      URL.revokeObjectURL(imageUrl.current);
    },
    [],
  );
  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (!ctx || !image.current || !dimensions.width) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, dimensions.width, dimensions.height);
    ctx.drawImage(image.current, 0, 0);
    ctx.fillStyle = "#111111";
    rects.forEach((r) => ctx.fillRect(r.x, r.y, r.width, r.height));
  }, [rects, dimensions]);
  function clear() {
    URL.revokeObjectURL(imageUrl.current);
    imageUrl.current = "";
    image.current = null;
    setFile(null);
    setRects([]);
    setReviewed(false);
    setDimensions({ width: 0, height: 0 });
    if (input.current) input.current.value = "";
  }
  function choose(candidate: File | undefined) {
    if (!candidate) return;
    if (!["image/png", "image/jpeg"].includes(candidate.type)) {
      onError("Choose a PNG or JPEG screenshot.");
      return;
    }
    if (candidate.size > MAX_SCREENSHOT_BYTES || candidate.size === 0) {
      onError("Screenshots must be nonempty and no larger than 2 MiB.");
      return;
    }
    URL.revokeObjectURL(imageUrl.current);
    const url = URL.createObjectURL(candidate);
    imageUrl.current = url;
    const img = new Image();
    img.onload = () => {
      if (imageUrl.current !== url) return;
      if (img.naturalWidth * img.naturalHeight > 4_000_000) {
        onError("Resize or crop this screenshot to four megapixels or fewer.");
        clear();
        return;
      }
      image.current = img;
      setFile(candidate);
      setRects([]);
      setReviewed(false);
      setDimensions({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.onerror = () => {
      onError("This file could not be decoded as an image.");
      clear();
    };
    img.src = url;
  }
  function point(event: PointerEvent<HTMLCanvasElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.round(
        Math.max(
          0,
          Math.min(
            dimensions.width,
            ((event.clientX - bounds.left) * dimensions.width) / bounds.width,
          ),
        ),
      ),
      y: Math.round(
        Math.max(
          0,
          Math.min(
            dimensions.height,
            ((event.clientY - bounds.top) * dimensions.height) / bounds.height,
          ),
        ),
      ),
    };
  }
  function box(a: { x: number; y: number }, b: { x: number; y: number }): Rect {
    return {
      x: Math.min(a.x, b.x),
      y: Math.min(a.y, b.y),
      width: Math.abs(a.x - b.x),
      height: Math.abs(a.y - b.y),
    };
  }
  function add(rect: Rect) {
    const safe = {
      x: Math.max(0, Math.min(dimensions.width - 1, rect.x)),
      y: Math.max(0, Math.min(dimensions.height - 1, rect.y)),
      width: Math.max(1, Math.min(dimensions.width - rect.x, rect.width)),
      height: Math.max(1, Math.min(dimensions.height - rect.y, rect.height)),
    };
    setRects((previous) => [...previous, safe]);
    setReviewed(false);
  }
  async function save() {
    if (!canvas.current || !file || !reviewed) return;
    setSaving(true);
    try {
      const type = file.type === "image/jpeg" ? "image/jpeg" : "image/png";
      const blob = await new Promise<Blob>((resolve, reject) =>
        canvas.current!.toBlob(
          (value) =>
            value
              ? resolve(value)
              : reject(new Error("Could not prepare screenshot.")),
          type,
          0.92,
        ),
      );
      if (blob.size > MAX_SCREENSHOT_BYTES)
        throw new Error(
          "The redacted image exceeds 2 MiB. Use a smaller crop.",
        );
      const name =
        file.name.replace(/\.[^.]+$/, "") +
        (type === "image/jpeg" ? ".jpg" : ".png");
      await onSave(blob, name);
      clear();
    } catch (error) {
      onError((error as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="screenshot-review">
      <input
        ref={input}
        className="visually-hidden"
        type="file"
        accept="image/png,image/jpeg"
        aria-label="Choose screenshot"
        onChange={(event) => choose(event.target.files?.[0])}
        disabled={busy || saving}
      />
      {!file ? (
        <button
          className="upload-screenshot"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          <span className="upload-icon">
            <ImagePlus size={22} />
          </span>
          <span>
            <strong>Add a screenshot</strong>
            <small>
              Review and redact before saving · PNG / JPEG · 2 MiB max
            </small>
          </span>
          <span className="upload-plus">+</span>
        </button>
      ) : (
        <div className="review-surface">
          <div className="review-heading">
            <div>
              <ShieldCheck size={17} />
              <strong>Review before you share</strong>
            </div>
            <button
              className="icon-button"
              aria-label="Discard screenshot preview"
              disabled={saving || busy}
              onClick={clear}
            >
              <X size={17} />
            </button>
          </div>
          <p className="evidence-copy">
            Drag over sensitive details to cover them with opaque rectangles.
            The original stays in this tab; only your reviewed version is saved.
          </p>
          <div className="redaction-canvas-wrap">
            <canvas
              ref={canvas}
              width={dimensions.width}
              height={dimensions.height}
              aria-label="Screenshot redaction canvas"
              onPointerDown={(event) => {
                if (busy || saving) return;
                event.currentTarget.setPointerCapture(event.pointerId);
                const p = point(event);
                setStart(p);
                setSelection(null);
              }}
              onPointerMove={(event) => {
                if (start) setSelection(box(start, point(event)));
              }}
              onPointerUp={(event) => {
                if (start) {
                  const r = box(start, point(event));
                  if (r.width > 1 && r.height > 1) add(r);
                  setStart(null);
                  setSelection(null);
                }
              }}
              onPointerCancel={() => {
                setStart(null);
                setSelection(null);
              }}
            />
            {selection && (
              <span
                className="redaction-selection"
                style={{
                  left: `${(selection.x / dimensions.width) * 100}%`,
                  top: `${(selection.y / dimensions.height) * 100}%`,
                  width: `${(selection.width / dimensions.width) * 100}%`,
                  height: `${(selection.height / dimensions.height) * 100}%`,
                }}
              />
            )}
          </div>
          <div className="redaction-tools">
            <span>
              <Eraser size={13} />
              {rects.length} redaction{rects.length !== 1 ? "s" : ""} ·{" "}
              {dimensions.width} × {dimensions.height}
            </span>
            <button
              className="text-button"
              disabled={!rects.length || saving || busy}
              onClick={() => {
                setRects(rects.slice(0, -1));
                setReviewed(false);
              }}
            >
              <Undo2 size={13} />
              Undo
            </button>
            <button
              className="text-button"
              disabled={!rects.length || saving || busy}
              onClick={() => {
                setRects([]);
                setReviewed(false);
              }}
            >
              <RotateCcw size={13} />
              Reset
            </button>
          </div>
          <details className="keyboard-redaction">
            <summary>Redact with keyboard coordinates</summary>
            <p className="evidence-copy">
              Coordinates are in original image pixels.
            </p>
            <div className="redaction-coordinates">
              {(["x", "y", "width", "height"] as const).map((field) => (
                <label key={field}>
                  {field.toUpperCase()}
                  <input
                    type="number"
                    min={field === "x" || field === "y" ? 0 : 1}
                    max={
                      field === "x" || field === "width"
                        ? dimensions.width
                        : dimensions.height
                    }
                    value={manual[field]}
                    onChange={(event) =>
                      setManual({
                        ...manual,
                        [field]: Math.max(0, Number(event.target.value)),
                      })
                    }
                  />
                </label>
              ))}
            </div>
            <button
              className="secondary-button"
              disabled={saving || busy}
              onClick={() => add(manual)}
            >
              Add opaque rectangle
            </button>
          </details>
          <label className="consent screenshot-confirm">
            <input
              type="checkbox"
              checked={reviewed}
              disabled={saving || busy}
              onChange={(event) => setReviewed(event.target.checked)}
            />
            <span>
              I reviewed this version and removed sensitive information. Save
              this reviewed image locally.
            </span>
          </label>
          <div className="review-actions">
            <span>Nothing is sent to the vision provider yet.</span>
            <button
              className="primary-button"
              disabled={!reviewed || busy || saving}
              onClick={save}
            >
              <Check size={15} />
              {saving ? "Saving…" : "Save reviewed screenshot"}
            </button>
          </div>
          <p className="fine-print">
            Unsaved previews and masks are lost if you reload this tab.
          </p>
        </div>
      )}
    </div>
  );
}
