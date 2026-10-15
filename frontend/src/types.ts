export type Project = {
  id: string;
  name: string;
  url: string;
  created_at: string;
};
export type Claim = {
  text: string;
  evidence_quote: string;
  source: string;
};
export type Report = {
  title: string;
  description: string;
  expected_behaviour: Claim | null;
  actual_behaviour: Claim | null;
  reproduction_steps: Claim[];
  observations: Claim[];
  hypotheses: string[];
  unknowns: string[];
  questions: string[];
  category: string;
  priority: string;
};
export type Attachment = {
  id: string;
  feedback_id: string;
  filename: string;
  mime_type: string;
  size: number;
  width: number;
  height: number;
  reviewed_at: string;
  analysis: {
    observations: { description: string; region: string }[];
    limitations: string[];
  } | null;
  analyzed_at: string | null;
  error: string | null;
};
export type Clarification = {
  id: string;
  question: string;
  answer: string;
  created_at: string;
};
export type Feedback = {
  id: string;
  project_id: string;
  attachments: Attachment[];
  clarifications: Clarification[];
  text: string;
  page_url: string;
  device: string;
  browser: string;
  status: string;
  report: Report | null;
  proposal: Report | null;
  version: number;
  error: string | null;
  created_at: string;
  updated_at: string;
};
export type Health = {
  status: string;
  ai_configured: boolean;
  free_tier_confirmed: boolean;
  model: string;
  busy: boolean;
  usage: {
    attempts: number;
    limit: number;
    paused: boolean;
    successful: number;
    vision_successful: number;
    input_tokens: number;
    output_tokens: number;
    average_latency_ms: number;
    resets: string;
  };
};
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "Cannot reach BugBrief. Check that the backend is running. Your input is kept in this browser.",
    );
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Please check the form fields and try again.",
    );
  }
  return response.json();
}
