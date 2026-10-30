import { useRef } from 'react';

/**
 * Lets a step field that is stored one way (a message string, a prompt with its bindings) be edited with the one chip
 * input, which speaks `Value`. While the stored form still means what the box last sent, the box is handed exactly that
 * value back, so typing never redraws it and the caret never jumps.
 */
export function useAsValue<S>(
  stored: S,
  toValue: (s: S) => unknown,
  fromValue: (v: unknown) => S,
  same: (a: S, b: S) => boolean = (a, b) => JSON.stringify(a) === JSON.stringify(b)
): [value: unknown, onChange: (v: unknown) => S] {
  const last = useRef<{ value: unknown; stored: S } | null>(null);
  const value = last.current && same(last.current.stored, stored) ? last.current.value : toValue(stored);
  const onChange = (v: unknown): S => {
    const next = fromValue(v);
    last.current = { value: v, stored: next };
    return next;
  };
  return [value, onChange];
}
