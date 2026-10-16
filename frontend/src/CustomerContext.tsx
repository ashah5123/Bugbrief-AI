import { Check, Globe, Monitor, UserRound } from "lucide-react";
import type { Feedback } from "./types";
export default function CustomerContext({ feedback }: { feedback: Feedback }) {
  const customer = feedback.customer;
  if (!customer) return null;
  const context = customer.context;
  return (
    <section className="agency-customer-context">
      <div className="evidence-section-title">
        <UserRound size={17} />
        <h3>Collected directly from the customer</h3>
      </div>
      <p>
        {customer.reporter_name || "Customer"} submitted this feedback. The
        original description, screenshots and answers were collected before
        agency review.
      </p>
      <dl>
        <div>
          <dt>Submitted</dt>
          <dd>
            {customer.submitted_at
              ? new Date(customer.submitted_at).toLocaleString()
              : "Not yet sent"}
          </dd>
        </div>
        <div>
          <dt>Captured from</dt>
          <dd>
            {context.source === "embedded"
              ? "Affected website"
              : context.source === "demo"
                ? "Demo preview · test context"
                : "Standalone form"}
          </dd>
        </div>
        <div>
          <dt>
            <Monitor size={12} />
            Viewport
          </dt>
          <dd>
            {context.viewport_width
              ? `${context.viewport_width} × ${context.viewport_height}`
              : "Not shared"}
          </dd>
        </div>
        <div>
          <dt>Screen</dt>
          <dd>
            {context.screen_width
              ? `${context.screen_width} × ${context.screen_height}`
              : "Not shared"}
          </dd>
        </div>
        <div>
          <dt>
            <Globe size={12} />
            Language / timezone
          </dt>
          <dd>
            {[context.language, context.timezone].filter(Boolean).join(" · ") ||
              "Not shared"}
          </dd>
        </div>
      </dl>
      {context.user_agent && (
        <details>
          <summary>Captured browser user agent</summary>
          <p>{context.user_agent}</p>
        </details>
      )}
      <div
        className={`context-confirmation ${context.same_browser_confirmed ? "confirmed" : ""}`}
      >
        <Check size={14} />
        {context.same_browser_confirmed
          ? "Customer confirmed this is the issue browser."
          : "Submission context only. The customer has not confirmed this is the issue browser."}
      </div>
      <small>
        A viewport and user agent do not identify a device model or prove what
        happened before capture.
      </small>
    </section>
  );
}
