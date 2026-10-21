export type FixDetails = { summary: string; location: string; steps: string };
export const emptyFix: FixDetails = { summary: "", location: "", steps: "" };
export const completeFix = (value: FixDetails) => Object.values(value).every(field => !!field.trim());

export function FixFields({ value, onChange, disabled, prefix = "" }: { value: FixDetails; onChange: (value: FixDetails) => void; disabled?: boolean; prefix?: string }) {
  return <fieldset className="fix-details-fields" disabled={disabled}>
    <legend>Customer-visible fix details</legend>
    <p>Explain the fix so the customer can test the right version. Keep credentials and private details out.</p>
    {([['summary', 'What changed', 1000], ['location', 'Where the fix is available', 1000], ['steps', 'Steps to retest', 2000]] as const).map(([key, label, limit]) => <label key={key}>
      {prefix}{label}
      <textarea aria-label={`${prefix}${label}`} rows={key === 'steps' ? 3 : 2} maxLength={limit} value={value[key]} onChange={event => onChange({ ...value, [key]: event.target.value })} />
    </label>)}
  </fieldset>;
}

export function FixSummary({ value }: { value?: FixDetails | null }) {
  return value ? <section className="fix-details-summary" aria-label="Fix details">
    <h3>What to test</h3>
    <dl>{([['summary', 'What changed'], ['location', 'Where the fix is available'], ['steps', 'Steps to retest']] as const).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{value[key]}</dd></div>)}</dl>
  </section> : null;
}
