export type GuidedAnswers = {
  goal: string;
  expected: string;
  steps: string;
  frequency: "" | "every_time" | "sometimes" | "once" | "not_sure";
};

export const emptyGuidedAnswers: GuidedAnswers = {
  goal: "", expected: "", steps: "", frequency: "",
};

export const frequencyLabels = {
  every_time: "Every time",
  sometimes: "Sometimes",
  once: "Only once",
  not_sure: "Not sure",
};

export const guidedLabels = {
  goal: "What were you trying to do?",
  expected: "What did you expect to happen?",
  steps: "Steps you took",
  frequency: "How often does it happen?",
};

export default function GuidedDetails({ details }: { details?: GuidedAnswers | null }) {
  if (!details || !Object.values(details).some(Boolean)) return null;
  return (
    <section className="guided-summary" aria-label="Customer's bug details">
      <h3>Details from the customer</h3>
      <dl>
        {(Object.keys(guidedLabels) as (keyof GuidedAnswers)[]).map((key) => (
          <div key={key}>
            <dt>{guidedLabels[key]}</dt>
            <dd>{key === "frequency"
              ? (details.frequency ? frequencyLabels[details.frequency] : "Not supplied")
              : details[key] || "Not supplied"}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
