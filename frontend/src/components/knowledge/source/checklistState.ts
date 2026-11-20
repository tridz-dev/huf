/** Per-source "next steps" checklist state, kept in localStorage (never throws). */
const key = (kind: 'armed' | 'dismissed', source: string) => `huf:kq-checklist-${kind}:${source}`;

function read(k: string): boolean {
  try {
    return localStorage.getItem(k) === '1';
  } catch {
    return false;
  }
}
function write(k: string, on: boolean) {
  try {
    if (on) localStorage.setItem(k, '1');
    else localStorage.removeItem(k);
  } catch {
    /* storage unavailable: the checklist just won't persist */
  }
}

export const checklistArmed = (source: string) => read(key('armed', source));
export const checklistDismissed = (source: string) => read(key('dismissed', source));
export const setChecklistArmed = (source: string) => write(key('armed', source), true);
export function setChecklistDismissed(source: string) {
  write(key('dismissed', source), true);
  write(key('armed', source), false);
}
