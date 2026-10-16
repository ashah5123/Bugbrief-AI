export type SavedSubmission = {
  access_token: string;
  project_name: string;
  reference: string;
  stage: string;
  account_owned?: boolean;
};
const manifestKey = "bugbrief-my-submissions";
export function savedSubmissions(): SavedSubmission[] {
  try {
    const data = JSON.parse(localStorage.getItem(manifestKey) || "[]");
    return Array.isArray(data)
      ? data.filter(
          (item) =>
            /^[A-Za-z0-9_-]{43}$/.test(item?.access_token) &&
            typeof item.project_name === "string" &&
            typeof item.reference === "string",
        )
      : [];
  } catch {
    return [];
  }
}
export function rememberSubmission(item: SavedSubmission) {
  if (item.account_owned) return;
  try {
    const items = savedSubmissions().filter(
      (saved) => saved.access_token !== item.access_token,
    );
    // Save only navigation metadata here; the private token grants access to this report.
    localStorage.setItem(
      manifestKey,
      JSON.stringify([
        {
          access_token: item.access_token,
          project_name: item.project_name,
          reference: item.reference,
          stage: item.stage,
        },
        ...items,
      ]),
    );
  } catch {
    /* A private return link also works without local storage. */
  }
}
export function forgetSubmission(token: string, preserveDraft = false) {
  try {
    localStorage.setItem(
      manifestKey,
      JSON.stringify(
        savedSubmissions().filter((item) => item.access_token !== token),
      ),
    );
    if (preserveDraft) return;
    for (const key of Object.keys(localStorage)) {
      if (!key.startsWith("bugbrief-customer-")) continue;
      try {
        if (
          JSON.parse(localStorage.getItem(key) || "null")?.access_token ===
          token
        )
          localStorage.removeItem(key);
      } catch {
        /* Ignore unrelated malformed local drafts. */
      }
    }
  } catch {
    /* Server-side deletion is authoritative. */
  }
}
