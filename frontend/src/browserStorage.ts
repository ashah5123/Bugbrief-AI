/** Browser persistence is optional; account switches must never inherit another person's drafts. */
export const browserStorage = {
  getItem(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  setItem(key: string, value: string) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* Private windows and embedded forms may block storage. */
    }
  },
  removeItem(key: string) {
    try {
      localStorage.removeItem(key);
    } catch {
      /* Server state remains authoritative. */
    }
  },
  keys(): string[] {
    try {
      return Object.keys(localStorage);
    } catch {
      return [];
    }
  },
};
const companyIdentity = "bugbrief-company-identity";
const customerIdentity = "bugbrief-customer-identity";
export function clearCompanyDrafts() {
  for (const key of browserStorage.keys()) {
    if (
      key === "bugbrief-draft" ||
      key === "bugbrief-active-id" ||
      key.startsWith("bugbrief-report-")
    )
      browserStorage.removeItem(key);
  }
  browserStorage.removeItem(companyIdentity);
}
export function activateCompany(identity: string) {
  if (browserStorage.getItem(companyIdentity) !== identity)
    clearCompanyDrafts();
  browserStorage.setItem(companyIdentity, identity);
}
export function clearCustomerDrafts() {
  for (const key of browserStorage.keys()) {
    if (
      key.startsWith("bugbrief-customer-") ||
      key === "bugbrief-my-submissions"
    )
      browserStorage.removeItem(key);
  }
  browserStorage.setItem(customerIdentity, "guest");
}
export function activateCustomer(identity: string) {
  const previous = browserStorage.getItem(customerIdentity);
  // Preserve guest capability/draft recovery when its holder creates an account.
  if (previous && previous !== "guest" && previous !== identity)
    clearCustomerDrafts();
  browserStorage.setItem(customerIdentity, identity);
}
