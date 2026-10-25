import { useRef } from "react";
import { ArrowRight } from "lucide-react";
import { nextStep } from "./NextStep";
import type { IssueWorkflow } from "./types";

export default function ReportAction({ workflow, hasCustomer, readOnly }: { workflow: IssueWorkflow; hasCustomer: boolean; readOnly: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const step = nextStep(workflow, 'company', hasCustomer);
  const assign = !workflow.waiting_since && workflow.status !== 'resolved' && !workflow.assigned_to;
  const conversation = !!workflow.waiting_since || (!assign && (['needs_information', 'resolved'].includes(workflow.status) || (workflow.status === 'ready_to_retest' && hasCustomer)));
  const label = readOnly ? (conversation ? 'View conversation' : 'View progress') : conversation ? (workflow.waiting_since ? 'Reply to customer' : 'Open conversation') : assign ? 'Assign employee' : workflow.status === 'in_progress' ? 'Prepare retest' : 'Review progress';
  return <div className="next-step report-action-bar" ref={ref} aria-label="Next report action" role="region">
    <div><span className="eyebrow">NEXT ACTION</span><strong>{step.title}</strong><p>{readOnly ? 'View-only access: ask a Contributor or Manager to make updates.' : step.detail}</p></div>
    <button type="button" className="primary-button" onClick={() => {
      const panel = ref.current?.closest<HTMLElement>('[data-report-panel]');
      const section = panel?.querySelector<HTMLElement>(conversation ? '.conversation-card' : '[aria-label="Assignment and progress"]');
      if (!section) return;
      const control = readOnly ? null : section.querySelector<HTMLElement>(conversation ? 'textarea:not(:disabled)' : assign ? 'select[aria-label="Assigned employee"]:not(:disabled)' : 'select[aria-label="Issue status"]:not(:disabled)');
      const target = control || section;
      if (!control) target.tabIndex = -1;
      target.focus({ preventScroll: true });
      target.scrollIntoView({ block: 'center', behavior: 'auto' });
    }}>{label}<ArrowRight size={14} /></button>
  </div>;
}
