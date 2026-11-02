import { SHORTCUTS, formatBinding } from '@/lib/shortcuts/registry';
import { detectPlatform } from '@/lib/shortcuts/platform';

/** "⌘Z" on a Mac, "Ctrl+Z" elsewhere, for a shortcut of the Flow editor list (the same list the "?" dialog shows). */
export function shortcutText(id: string): string {
  const entry = SHORTCUTS.find((s) => s.id === id);
  if (!entry) return '';
  const platform = detectPlatform();
  const keys = entry.keys ?? formatBinding(entry.binding, platform);
  return platform === 'mac' ? keys.map((k) => (k === 'Shift' ? '\u21e7' : k)).join('') : keys.join('+');
}

/** A tooltip with its shortcut: "Undo: moved a step (⌘Z)". */
export function withShortcut(text: string, id: string): string {
  const hint = shortcutText(id);
  return hint ? `${text} (${hint})` : text;
}
