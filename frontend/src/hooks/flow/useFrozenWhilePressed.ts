import { useEffect, useRef, useState } from 'react';

/**
 * Returns `value`, except that while a mouse button or finger is held down anywhere it keeps the value it had.
 *
 * Why: leaving a field commits what was typed, which can change how many things are left to finish, which can add or
 * remove words in the header, which moves the buttons beside them. If that happens between pressing Save and letting
 * go, the click lands on a different button and is lost. Holding the old value until the press is over avoids it.
 */
export function useFrozenWhilePressed<T>(value: T): T {
  const [shown, setShown] = useState(value);
  const pressed = useRef(false);
  const latest = useRef(value);
  latest.current = value;

  useEffect(() => {
    const down = () => {
      pressed.current = true;
    };
    // After the click has been delivered (it follows the release in the same turn), let go and catch up.
    const up = () => {
      setTimeout(() => {
        pressed.current = false;
        setShown(latest.current);
      }, 0);
    };
    window.addEventListener('pointerdown', down, true);
    window.addEventListener('pointerup', up, true);
    window.addEventListener('pointercancel', up, true);
    return () => {
      window.removeEventListener('pointerdown', down, true);
      window.removeEventListener('pointerup', up, true);
      window.removeEventListener('pointercancel', up, true);
    };
  }, []);

  useEffect(() => {
    if (!pressed.current) setShown(value);
  }, [value]);

  return shown;
}
