import { useEffect, useRef } from 'react';
import { detectPlatform } from './platform';
import { matchesBinding, shouldHandleShortcut, type ShortcutBinding } from './matching';

const DEFAULT_ALWAYS_ALLOW = ['Escape'];

export interface UseKeyboardShortcutOptions {
  enabled?: boolean;
  /** Fire even when focus is in an input/textarea/contenteditable. */
  allowInEditable?: boolean;
  /** Keys allowed regardless of focus. Defaults to ["Escape"]. */
  alwaysAllowKeys?: string[];
  /** Scope the listener to a container instead of the whole window. */
  target?: React.RefObject<HTMLElement>;
}

/**
 * Binds a single keyboard shortcut. Ignores keydowns while focus is in an
 * editable element unless `allowInEditable` or `alwaysAllowKeys` say
 * otherwise, and cleans up on unmount.
 */
export function useKeyboardShortcut(
  binding: ShortcutBinding,
  handler: (event: KeyboardEvent) => void,
  opts: UseKeyboardShortcutOptions = {}
): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  const {
    enabled = true,
    allowInEditable = false,
    alwaysAllowKeys = DEFAULT_ALWAYS_ALLOW,
    target,
  } = opts;

  const bindingKey = binding.key;
  const bindingMod = binding.mod;
  const bindingShift = binding.shift;
  const bindingAlt = binding.alt;

  useEffect(() => {
    if (!enabled) return;

    const el: Window | HTMLElement = target?.current ?? window;

    const listener = (event: Event) => {
      const keyboardEvent = event as KeyboardEvent;
      const platform = detectPlatform();
      const currentBinding: ShortcutBinding = {
        key: bindingKey,
        mod: bindingMod,
        shift: bindingShift,
        alt: bindingAlt,
      };

      if (!matchesBinding(keyboardEvent, currentBinding, platform)) return;
      if (
        !shouldHandleShortcut({
          target: keyboardEvent.target as HTMLElement | null,
          key: keyboardEvent.key,
          allowInEditable,
          alwaysAllowKeys,
        })
      ) {
        return;
      }

      keyboardEvent.preventDefault();
      handlerRef.current(keyboardEvent);
    };

    el.addEventListener('keydown', listener);
    return () => el.removeEventListener('keydown', listener);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bindingKey, bindingMod, bindingShift, bindingAlt, enabled, allowInEditable, target]);
}
