import type { ShortcutBinding } from './matching';
import { getModifierKey, type Platform } from './platform';

export type ShortcutScope = 'Global' | 'Chat' | 'Sidebar' | 'Playground';

export interface ShortcutDescriptor {
  id: string;
  binding: ShortcutBinding;
  description: string;
  scope: ShortcutScope;
}

/**
 * Central, typed list of every real keyboard shortcut in the app. This
 * drives the "?" help dialog. A handful are bound elsewhere (sidebar
 * toggle in `components/ui/sidebar.tsx`, save in `useSaveShortcut`, submit
 * in `ChatInput`) — they're listed here purely for discoverability, not
 * re-bound, to avoid double listeners.
 */
export const SHORTCUTS: ShortcutDescriptor[] = [
  {
    id: 'shortcuts-help',
    binding: { key: '?' },
    description: 'Show keyboard shortcuts',
    scope: 'Global',
  },
  {
    id: 'sidebar-toggle',
    binding: { key: 'b', mod: true },
    description: 'Toggle sidebar',
    scope: 'Global',
  },
  {
    id: 'save',
    binding: { key: 's', mod: true },
    description: 'Save',
    scope: 'Global',
  },
  {
    id: 'close-dialog',
    binding: { key: 'Escape' },
    description: 'Close dialog or popover',
    scope: 'Global',
  },
  {
    id: 'chat-send',
    binding: { key: 'Enter' },
    description: 'Send message',
    scope: 'Chat',
  },
  {
    id: 'chat-newline',
    binding: { key: 'Enter', shift: true },
    description: 'Insert new line',
    scope: 'Chat',
  },
  {
    id: 'playground-copy-a-to-b',
    binding: { key: 'c', mod: true, shift: true },
    description: 'Copy A → B',
    scope: 'Playground',
  },
  {
    id: 'playground-swap',
    binding: { key: 'x', mod: true, shift: true },
    description: 'Swap A and B',
    scope: 'Playground',
  },
  {
    id: 'playground-toggle-diff',
    binding: { key: 'd', mod: true, shift: true },
    description: 'Toggle diff responses',
    scope: 'Playground',
  },
];

/** Renders a binding as the ordered list of key labels for a given platform. */
export function formatBinding(binding: ShortcutBinding, platform: Platform): string[] {
  const mod = getModifierKey(platform);
  const labels: string[] = [];

  if (binding.mod) labels.push(mod.mod);
  if (binding.alt) labels.push(mod.alt);
  if (binding.shift) labels.push('Shift');

  labels.push(formatKeyLabel(binding.key));

  return labels;
}

function formatKeyLabel(key: string): string {
  if (key === ' ') return 'Space';
  if (key.length === 1) return key.toUpperCase();
  return key;
}
