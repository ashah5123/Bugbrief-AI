import { useEffect, useId, useState } from "react";
import {
  ArrowUpRight,
  Check,
  Image,
  LoaderCircle,
  MessageSquare,
  ShieldCheck,
  Sparkles,
  Trash2,
} from "lucide-react";
import { api, type Feedback } from "./types";
import ScreenshotReview from "./ScreenshotReview";

type Props = {
  feedback: Feedback | null;
  ensureFeedback: () => Promise<Feedback>;
  onChange: (feedback: Feedback) => void;
  busy: boolean;
  onBusy: (busy: boolean) => void;
  questions?: string[];
};
export default function EvidencePanel({
  feedback,
  ensureFeedback,
  onChange,
  busy,
  onBusy,
  questions,
}: Props) {
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [visionConsent, setVisionConsent] = useState(false);
  const [working, setWorking] = useState("");
  const [question, setQuestion] = useState("Additional context or correction");
  const [answer, setAnswer] = useState("");
  const consentId = useId();
  const attachments = feedback?.attachments || [];
  const history = feedback?.clarifications || [];
  const suggested =
    questions ||
    feedback?.proposal?.questions ||
    feedback?.report?.questions ||
    [];
  const unanswered = suggested.filter(
    (q) => !history.some((entry) => entry.question === q),
  );
  useEffect(() => {
    setVisionConsent(false);
    setError("");
    setMessage("");
    try {
      const saved = JSON.parse(
        localStorage.getItem(`bugbrief-answer-${feedback?.id || "new"}`) ||
          "null",
      );
      setQuestion(saved?.question || "Additional context or correction");
      setAnswer(saved?.answer || "");
    } catch {
      setQuestion("Additional context or correction");
      setAnswer("");
    }
  }, [feedback?.id]);
  function store(q: string, a: string) {
    setQuestion(q);
    setAnswer(a);
    localStorage.setItem(
      `bugbrief-answer-${feedback?.id || "new"}`,
      JSON.stringify({ question: q, answer: a }),
    );
  }
  async function change(
    label: string,
    operation: (item: Feedback) => Promise<Feedback>,
  ) {
    if (working || busy) return;
    setError("");
    setMessage("");
    setWorking(label);
    onBusy(true);
    try {
      const current = await ensureFeedback();
      const updated = await operation(current);
      onChange(updated);
      return updated;
    } catch (e) {
      setError((e as Error).message);
      throw e;
    } finally {
      setWorking("");
      onBusy(false);
    }
  }
  async function upload(blob: Blob, name: string) {
    const result = await change("upload", async (current) => {
      const response = await fetch(
        `/api/feedback/${current.id}/attachments?reviewed=true&filename=${encodeURIComponent(name)}`,
        { method: "POST", headers: { "Content-Type": blob.type }, body: blob },
      );
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(
          body.detail ||
            "Screenshot could not be saved. Your reviewed preview is still here.",
        );
      }
      return response.json() as Promise<Feedback>;
    });
    if (result)
      setMessage(
        "Reviewed screenshot saved locally. External analysis is a separate action.",
      );
  }
  return (
    <section
      className="evidence-panel"
      aria-label="Screenshots and clarification"
    >
      <div className="evidence-section-title">
        <Image size={16} />
        <h3>Show what you see.</h3>
        <span>{attachments.length} / 3 screenshots</span>
      </div>
      <p className="evidence-copy">
        Add visual context without guessing what happened before it.
      </p>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <p className="evidence-success" role="status">
          <Check size={14} />
          {message}
        </p>
      )}
      {attachments.map((image) => (
        <article className="attachment-card" key={image.id}>
          <a
            href={`/api/feedback/${feedback!.id}/attachments/${image.id}/content`}
            target="_blank"
            rel="noreferrer"
            className="attachment-preview"
            aria-label={`View screenshot ${image.filename}`}
          >
            <img
              src={`/api/feedback/${feedback!.id}/attachments/${image.id}/content`}
              alt={`Reviewed screenshot: ${image.filename}`}
            />
            <span>
              <ArrowUpRight size={14} />
            </span>
          </a>
          <div className="attachment-details">
            <div className="attachment-title">
              <strong>{image.filename}</strong>
              <button
                className="icon-button"
                aria-label={`Delete screenshot ${image.filename}`}
                disabled={busy}
                onClick={() =>
                  change(image.id, (current) =>
                    api<Feedback>(
                      `/feedback/${current.id}/attachments/${image.id}`,
                      "DELETE",
                    ),
                  )
                    .then((result) => {
                      if (result)
                        setMessage(
                          "Screenshot deleted. Saved reports are preserved and need review.",
                        );
                    })
                    .catch(() => {})
                }
              >
                <Trash2 size={15} />
              </button>
            </div>
            <p>
              {image.width} × {image.height} · {(image.size / 1024).toFixed(0)}{" "}
              KiB · <ShieldCheck size={11} /> Reviewed
            </p>
            {image.analysis ? (
              <div className="vision-observations">
                <span className="vision-label">
                  <Sparkles size={12} /> Machine observations · verify visually
                </span>
                {image.analysis.observations.length ? (
                  <ul>
                    {image.analysis.observations.map((observation, index) => (
                      <li key={index}>
                        <strong>{observation.region}</strong>{" "}
                        {observation.description}
                        <code>
                          Screenshot {attachments.indexOf(image) + 1} ·
                          observation {index + 1}
                        </code>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>No reliable visible observations were found.</p>
                )}
                <details>
                  <summary>What this image cannot establish</summary>
                  <ul>
                    {image.analysis.limitations.map((limitation, index) => (
                      <li key={index}>{limitation}</li>
                    ))}
                  </ul>
                </details>
              </div>
            ) : (
              <>
                <span className="local-only-label">
                  Saved locally · not analyzed
                </span>
                <button
                  className="secondary-button analyze-image"
                  disabled={!visionConsent || busy}
                  onClick={() =>
                    change(image.id, (current) =>
                      api<Feedback>(
                        `/feedback/${current.id}/attachments/${image.id}/analyze`,
                        "POST",
                        { consent: visionConsent },
                      ),
                    )
                      .then((result) => {
                        if (result)
                          setMessage(
                            "Screenshot observations saved. Verify them before revising the report.",
                          );
                      })
                      .catch(() => {})
                  }
                >
                  {working === image.id ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : (
                    <Sparkles size={14} />
                  )}
                  Analyze reviewed screenshot
                </button>
              </>
            )}
            {image.error && <p className="attachment-error">{image.error}</p>}
          </div>
        </article>
      ))}
      {attachments.some((image) => !image.analysis) && (
        <label className="consent vision-consent" htmlFor={consentId}>
          <input
            id={consentId}
            type="checkbox"
            checked={visionConsent}
            onChange={(event) => setVisionConsent(event.target.checked)}
          />
          <span>
            I agree to send the saved, reviewed screenshot to Gemini. Free-tier
            inputs and outputs may be used for product improvement and human
            review.
          </span>
        </label>
      )}
      {attachments.length < 3 && (
        <ScreenshotReview busy={busy} onSave={upload} onError={setError} />
      )}
      {attachments.some((image) => !image.analysis) && (
        <p className="fine-print">
          Analyze or delete each screenshot before generating a report. Saving
          and answering questions work without provider access.
        </p>
      )}
      <details
        className="clarification-section"
        open={history.length > 0 || unanswered.length > 0}
      >
        <summary>
          <div className="evidence-section-title">
            <MessageSquare size={16} />
            <h3>Fill in the gaps.</h3>
            <span>{history.length} / 20 answers</span>
          </div>
        </summary>
        <p className="evidence-copy">
          Answers stay with the original feedback. Unknown is a useful answer,
          too.
        </p>
        {unanswered.length > 0 && (
          <div className="suggested-questions">
            <span className="vision-label">SUGGESTED QUESTIONS</span>
            {unanswered.map((q, index) => (
              <button
                key={index}
                className={question === q ? "chosen" : ""}
                disabled={busy}
                onClick={() => store(q, answer)}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                {q}
              </button>
            ))}
          </div>
        )}
        {history.length > 0 && (
          <details className="clarification-history" open>
            <summary>Saved clarification history · {history.length}</summary>
            {history.map((entry, index) => (
              <div className="answer-history" key={entry.id}>
                <span className="answer-number">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <h4>{entry.question}</h4>
                  <p>{entry.answer}</p>
                  <small>{new Date(entry.created_at).toLocaleString()}</small>
                  <code>Answer {index + 1} · available as report evidence</code>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => store(entry.question, "")}
                  >
                    Add a correction
                  </button>
                </div>
              </div>
            ))}
          </details>
        )}
        <div className="answer-form">
          <label>
            Question or context
            <input
              maxLength={500}
              value={question}
              onChange={(event) => store(event.target.value, answer)}
              placeholder="What detail can you add?"
            />
          </label>
          <label>
            Your clarification
            <textarea
              rows={3}
              maxLength={2000}
              value={answer}
              onChange={(event) => store(question, event.target.value)}
              placeholder="e.g. Chrome on Android. It happens every time after tapping Pay now."
            />
          </label>
          <div className="answer-actions">
            <span>Saved locally. No external request.</span>
            <button
              className="secondary-button"
              disabled={
                busy ||
                question.trim().length < 3 ||
                !answer.trim() ||
                history.length >= 20
              }
              onClick={() =>
                change("answer", (current) =>
                  api<Feedback>(
                    `/feedback/${current.id}/clarifications`,
                    "POST",
                    { question, answer },
                  ),
                )
                  .then((result) => {
                    if (result) {
                      store("Additional context or correction", "");
                      setMessage(
                        "Clarification saved. Generate a revised report when you’re ready.",
                      );
                    }
                  })
                  .catch(() => {})
              }
            >
              {working === "answer" ? (
                <LoaderCircle className="spin" size={14} />
              ) : (
                <Check size={14} />
              )}
              Save answer
            </button>
          </div>
        </div>
      </details>
    </section>
  );
}
