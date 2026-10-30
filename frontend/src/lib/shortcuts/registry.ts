import type { ShortcutBinding } from './matching';
import { getModifierKey, type Platform } from './platform';

export type ShortcutScope = 'Global' | 'Flow editor' | 'Chat' | 'Sidebar' | 'Playground';

export interface ShortcutDescriptor {
  id: string;
  binding: ShortcutBinding;
  description: string;
  scope: ShortcutScope;
  /** Key labels to show instead of the binding (mouse gestures such as Shift + click). */
  keys?: string[];
}

/**
 * Central, typed list of every real keyboard shortcut in the app. This
 * drives the "?" help dialog. A handful are bound elsewhere (sidebar
 * toggle in `components/ui/sidebar.tsx`, save in `useSaveShortcut`, submit
 * in `ChatInput`) — they're listed here purely for discoverability, not
 * re-bound, to avoid double listeners.
 */
export const SHORTCUTS: ShortcutDescriptor[] = [
  // ── Flow editor ──────────────────────────────────────────────────────
  { id: 'flow-palette', binding: { key: 'k', mod: true }, description: 'Search steps, flows and actions', scope: 'Flow editor' },
  { id: 'flow-save', binding: { key: 's', mod: true }, description: 'Save the flow', scope: 'Flow editor' },
  { id: 'flow-run', binding: { key: 'Enter', mod: true }, description: 'Run a test of the flow', scope: 'Flow editor' },
  { id: 'flow-undo', binding: { key: 'z', mod: true }, description: 'Undo', scope: 'Flow editor' },
  { id: 'flow-redo', binding: { key: 'z', mod: true, shift: true }, description: 'Redo', scope: 'Flow editor' },
  { id: 'flow-redo-alt', binding: { key: 'y', mod: true }, description: 'Redo (another way)', scope: 'Flow editor' },
  { id: 'flow-duplicate', binding: { key: 'd', mod: true }, description: 'Duplicate the selected step', scope: 'Flow editor' },
  { id: 'flow-copy', binding: { key: 'c', mod: true }, description: 'Copy the selected steps', scope: 'Flow editor' },
  { id: 'flow-paste', binding: { key: 'v', mod: true }, description: 'Paste steps, also into another flow', scope: 'Flow editor' },
  { id: 'flow-select-all', binding: { key: 'a', mod: true }, description: 'Select every step', scope: 'Flow editor' },
  { id: 'flow-delete', binding: { key: 'Delete' }, description: 'Delete the selected step (asks first)', scope: 'Flow editor' },
  { id: 'flow-multi-click', binding: { key: 'Click', shift: true }, keys: ['Shift', 'Click'], description: 'Select several steps', scope: 'Flow editor' },
  { id: 'flow-multi-drag', binding: { key: 'Drag', shift: true }, keys: ['Shift', 'Drag'], description: 'Select steps with a box', scope: 'Flow editor' },
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
