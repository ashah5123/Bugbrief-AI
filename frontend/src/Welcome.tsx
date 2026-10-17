import {
  ArrowRight,
  Building2,
  MessageSquare,
  ShieldCheck,
} from "lucide-react";
export function Welcome() {
  return (
    <div className="welcome-shell">
      <a className="welcome-brand" href="/">
        b<span>✳</span> bugbrief
      </a>
      <main className="welcome-main">
        <span className="eyebrow">A CLEARER PATH TO GETTING IT FIXED</span>
        <h1>
          Welcome. What brings
          <br />
          you here?
        </h1>
        <p>Choose where you belong. We’ll take you from there.</p>
        <div className="role-options">
          <a className="role-option" href="/workspace?employee=choose">
            <span className="role-icon">
              <Building2 size={28} />
            </span>
            <span className="eyebrow">COMPANY WORKSPACE</span>
            <h2>I’m with the company</h2>
            <p>
              Collect customer feedback, review reports and give your developers
              the details they need.
            </p>
            <span className="role-cta">
              Open company workspace <ArrowRight size={17} />
            </span>
          </a>
          <a className="role-option customer-option" href="/customer">
            <span className="role-icon">
              <MessageSquare size={28} />
            </span>
            <span className="eyebrow">CUSTOMER PORTAL</span>
            <h2>I’m a customer</h2>
            <p>
              Report something that went wrong, add helpful details or return to
              your own reports.
            </p>
            <span className="role-cta">
              Continue as a customer <ArrowRight size={17} />
            </span>
          </a>
        </div>
        <span className="welcome-footnote">
          <ShieldCheck size={14} /> Company access stays protected. Customer
          reports stay private.
        </span>
      </main>
    </div>
  );
}
