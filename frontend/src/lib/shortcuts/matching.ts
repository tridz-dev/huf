import type { Platform } from './platform';

/**
 * A key combination to match against a keydown event.
 * Modifier fields are optional: omit one to ignore it entirely (useful for
 * symbol keys like "?" where the shift state is already encoded in the
 * character), or set it explicitly (true/false) to require an exact match.
 */
export interface ShortcutBinding {
  key: string;
  /** Cmd on Mac, Ctrl on Windows/Linux. */
  mod?: boolean;
  shift?: boolean;
  alt?: boolean;
}

export interface MatchableEvent {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
}

export function matchesBinding(
  event: MatchableEvent,
  binding: ShortcutBinding,
  platform: Platform
): boolean {
  if (event.key.toLowerCase() !== binding.key.toLowerCase()) return false;

  if (binding.mod !== undefined) {
    const modPressed = platform === 'mac' ? event.metaKey : event.ctrlKey;
    if (modPressed !== binding.mod) return false;
  }

  if (binding.shift !== undefined && event.shiftKey !== binding.shift) return false;
  if (binding.alt !== undefined && event.altKey !== binding.alt) return false;

  return true;
}

export interface FocusTarget {
  tagName?: string;
  isContentEditable?: boolean;
}

const EDITABLE_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

export function isEditableTarget(target: FocusTarget | null | undefined): boolean {
  if (!target) return false;
  if (target.isContentEditable) return true;
  return !!target.tagName && EDITABLE_TAGS.has(target.tagName.toUpperCase());
}

export interface ShouldHandleOptions {
  target: FocusTarget | null | undefined;
  key: string;
  /** Allow the shortcut to fire even while focus is in an editable element. */
  allowInEditable?: boolean;
  /** Keys that are always allowed regardless of focus (e.g. Escape). */
  alwaysAllowKeys?: string[];
}

/**
 * Decides whether a global shortcut should fire given where focus currently
 * is. Typing in an input/textarea/contenteditable suppresses shortcuts
 * unless explicitly allowed.
 */
export function shouldHandleShortcut(opts: ShouldHandleOptions): boolean {
  if (!isEditableTarget(opts.target)) return true;
  if (opts.allowInEditable) return true;
  return !!opts.alwaysAllowKeys?.some((k) => k.toLowerCase() === opts.key.toLowerCase());
}
