import { useEffect, useRef, useState } from 'react';

const DEFAULT_CHAR_MS = 35;

export function getTypewriterSlice(text: string, index: number): string {
  return text.slice(0, Math.max(0, index));
}

export function useTypewriterText(
  targetText: string,
  options?: { enabled?: boolean; charMs?: number }
) {
  const enabled = options?.enabled ?? false;
  const charMs = options?.charMs ?? DEFAULT_CHAR_MS;
  const [displayText, setDisplayText] = useState(targetText);
  const targetRef = useRef(targetText);
  const enabledRef = useRef(enabled);

  targetRef.current = targetText;
  enabledRef.current = enabled;

  useEffect(() => {
    if (!enabled) {
      setDisplayText(targetText);
      return;
    }

    let index = 0;
    setDisplayText('');

    const timerId = window.setInterval(() => {
      index += 1;
      const next = getTypewriterSlice(targetRef.current, index);
      setDisplayText(next);

      if (index >= targetRef.current.length) {
        window.clearInterval(timerId);
      }
    }, charMs);

    return () => {
      window.clearInterval(timerId);
    };
  }, [enabled, targetText, charMs]);

  return displayText;
}
