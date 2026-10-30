/**
 * Screen-reader announcements for the editor ("Step duplicated", "Undid: moved a step"). Callers say what happened; one polite
 * live region (mounted once by the editor) reads it out. A message said twice in a row is still read twice.
 */
type Listener = (message: string) => void;

const listeners = new Set<Listener>();
let counter = 0;

export function announce(message: string): void {
  // A trailing non-breaking space makes the second identical message a real change for the live region.
  const text = counter++ % 2 === 0 ? message : `${message} `;
  listeners.forEach((l) => l(text));
}

export function onAnnounce(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
