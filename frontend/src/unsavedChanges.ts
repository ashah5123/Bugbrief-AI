import { useLayoutEffect, useRef } from "react";

type Entry = { scope: string; label: string; dirty: boolean; busy: boolean };
const entries = new Map<symbol, Entry>();
let listening = false;
let skipUnload = false;
const active = (scopes?: string[]) => [...entries.values()].filter(entry => (entry.dirty || entry.busy) && (!scopes || scopes.includes(entry.scope)));

export function confirmUnsaved(scopes?: string[], exceptScopes: string[] = []) {
  const changes = active(scopes).filter(entry => !exceptScopes.includes(entry.scope));
  if (changes.some(entry => entry.busy)) {
    window.alert("Please wait for the current save or send to finish before leaving.");
    return false;
  }
  if (!changes.length) return true;
  const labels = [...new Set(changes.map(entry => entry.label))].join(", ");
  return window.confirm(`You have unsaved ${labels}. Leave without saving? Unsent work in this tab may be lost.`);
}

// Used only after an explicit confirmation, or for mandatory identity/access changes.
export function allowPageExit(action: () => void) {
  skipUnload = true;
  try { action(); } finally { window.setTimeout(() => { skipUnload = false; }, 0); }
}

function beforeUnload(event: BeforeUnloadEvent) {
  if (skipUnload) { skipUnload = false; return; }
  if (!active().length) return;
  event.preventDefault();
  event.returnValue = "";
}

function followLink(event: MouseEvent) {
  if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
  if (!link || link.hasAttribute("download") || (link.target && link.target !== "_self")) return;
  const target = new URL(link.href, location.href);
  if (!['http:', 'https:'].includes(target.protocol)) return;
  if (target.origin === location.origin && target.pathname === location.pathname && target.search === location.search && (target.hash || link.getAttribute("href")?.startsWith("#"))) return;
  if (!confirmUnsaved()) { event.preventDefault(); return; }
  event.preventDefault();
  allowPageExit(() => location.assign(target.href));
}

function syncListeners() {
  const needed = active().length > 0;
  if (needed === listening) return;
  listening = needed;
  if (needed) { window.addEventListener("beforeunload", beforeUnload); document.addEventListener("click", followLink); }
  else { window.removeEventListener("beforeunload", beforeUnload); document.removeEventListener("click", followLink); }
}

export function useUnsavedChanges(scope: string, label: string, dirty: boolean, busy = false) {
  const token = useRef(Symbol(label));
  useLayoutEffect(() => {
    entries.set(token.current, { scope, label, dirty, busy });
    syncListeners();
  });
  useLayoutEffect(() => () => { entries.delete(token.current); syncListeners(); }, []);
}
