import type { IssueWorkflow } from "./types";

type Audience = "company" | "customer";
export function nextStep(workflow: IssueWorkflow | null | undefined, audience: Audience, hasCustomer = true) {
  if (!workflow) return {
    title: audience === "customer" ? "Finish and send your report" : "Review this feedback",
    detail: audience === "customer" ? "Your draft has not reached the team yet. Open it to finish and send." : "Check the submitted details before planning the work.",
  };
  if (audience === "customer") {
    switch (workflow.status) {
      case "needs_information": return { title: "Reply with the requested details", detail: "Open your report, read the team’s question, and send your reply." };
      case "ready_to_retest": return { title: "Try the fix", detail: "Repeat the original steps, then choose “It works” or “Still happening”." };
      case "resolved": return { title: "Your issue is resolved", detail: "No action needed. You can still open the report and message the team." };
      case "in_progress": return { title: "The team is working on it", detail: workflow.assigned_to ? `${workflow.assigned_to.name} is handling this issue. You can add details in the conversation.` : "The team is investigating. You can add details in the conversation." };
      default: return { title: "Your report is with the team", detail: "You don’t need to send it again. The team will post updates here." };
    }
  }
  if (workflow.waiting_since) return { title: "Reply to the customer", detail: "Their latest report or message still needs a public response. Private notes won’t reach them." };
  if (workflow.status !== "resolved" && !workflow.assigned_to) return { title: "Assign an employee", detail: "Choose someone from this project to own the next update before progressing the issue." };
  switch (workflow.status) {
    case "resolved": return { title: "Resolved", detail: "No action needed. Reopen the issue if further work is required." };
    case "ready_to_retest": return { title: hasCustomer ? "Waiting for customer retest" : "Verify the fix", detail: hasCustomer ? "The customer can confirm the fix or tell you what is still happening." : "Repeat the reported steps and resolve the issue when the fix is confirmed." };
    case "needs_information": return { title: hasCustomer ? "Waiting for customer details" : "Gather the missing details", detail: hasCustomer ? "Check the conversation for their reply before continuing the work." : "Review the requested information and add a clarification before continuing." };
    case "in_progress": return { title: "Investigate and share an update", detail: "Keep the customer informed. When the fix is ready, request a retest." };
    default: return workflow.assigned_to ? { title: "Review the report", detail: `${workflow.assigned_to.name} owns this issue. Review the evidence and start investigating.` } : { title: "Assign an employee", detail: "Choose someone from this project to review the report and own the next update." };
  }
}
export default function NextStep({ workflow, audience, hasCustomer, compact = false }: {
  workflow?: IssueWorkflow | null; audience: Audience; hasCustomer?: boolean; compact?: boolean;
}) {
  const step = nextStep(workflow, audience, hasCustomer);
  return <div className={`next-step ${compact ? "next-step-compact" : ""}`}>
    {!compact && <span className="eyebrow">WHAT HAPPENS NEXT</span>}
    <strong>{step.title}</strong>
    {!compact && <p>{step.detail}</p>}
  </div>;
}
