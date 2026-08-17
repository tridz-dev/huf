import { useCallback, useEffect, useState } from 'react';

function readStored(key: string, defaultValue: boolean): boolean {
  try {
    const stored = window.localStorage.getItem(key);
    return stored === null ? defaultValue : stored === '1';
  } catch {
    // localStorage unavailable (private mode, etc.) - fall back to the default.
    return defaultValue;
  }
}

/**
 * Persist a boolean flag (e.g. a collapsible sidebar section's expanded
 * state) to localStorage under `key`. Re-reads from storage whenever `key`
 * changes, so callers that switch between scope-specific keys (e.g. a
 * global vs. project-scoped variant of the same setting) pick up the
 * right persisted value instead of carrying over the previous key's state.
 */
export function useLocalStorageBoolean(
  key: string,
  defaultValue: boolean
): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState<boolean>(() => readStored(key, defaultValue));

  useEffect(() => {
    setValue(readStored(key, defaultValue));
    // Only the key identifies which persisted value to load; a caller
    // passing a fresh `defaultValue` literal each render shouldn't
    // re-trigger this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const update = useCallback(
    (next: boolean) => {
      setValue(next);
      try {
        window.localStorage.setItem(key, next ? '1' : '0');
      } catch {
        // localStorage unavailable (private mode, etc.) - preference just won't persist.
      }
    },
    [key]
  );

  return [value, update];
}
