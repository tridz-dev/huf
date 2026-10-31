import * as React from 'react';

/**
 * A Radix menu or popover stays mounted while it fades out (about 150 ms). Its "click outside closes me" listener is still
 * alive then, so a click on the button that opens it again, right after it closed (choose an item, press Escape, undo, then
 * click the button), opens it and the fading copy closes it two milliseconds later: the button seems dead.
 *
 * The guard asks one question: was this menu open BEFORE the click started? A document listener in the capture phase notes
 * that before any handler runs (the opening handler has re-rendered the content as "open" by the time the outside-click check
 * runs). A click that started while the menu was fading does not count as an outside click on it. An open menu is not affected.
 */
export function useClosingGuard<T extends HTMLElement>(forwarded: React.ForwardedRef<T>) {
  const own = React.useRef<T | null>(null);
  const wasOpen = React.useRef(true);
  const ref = React.useCallback(
    (node: T | null) => {
      own.current = node;
      if (typeof forwarded === 'function') forwarded(node);
      else if (forwarded) forwarded.current = node;
    },
    [forwarded]
  );
  React.useEffect(() => {
    const note = () => {
      wasOpen.current = own.current?.dataset.state !== 'closed';
    };
    document.addEventListener('pointerdown', note, true);
    return () => document.removeEventListener('pointerdown', note, true);
  }, []);
  const guard = React.useCallback((event: Event) => {
    if (!wasOpen.current) event.preventDefault();
  }, []);
  return { ref, guard };
}

/** Run the caller's own handler first, then the guard. */
export function withGuard<E extends Event>(own: ((event: E) => void) | undefined, guard: (event: Event) => void) {
  return (event: E) => {
    own?.(event);
    if (!event.defaultPrevented) guard(event);
  };
}
