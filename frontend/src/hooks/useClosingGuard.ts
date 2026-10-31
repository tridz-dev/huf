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
    let timer: ReturnType<typeof setTimeout> | undefined;
    const rearm = () => {
      if (timer) clearTimeout(timer);
      timer = undefined;
      wasOpen.current = true;
    };
    const note = () => {
      wasOpen.current = own.current?.dataset.state !== 'closed';
      // The answer is only meant for the outside-click check of THIS press. Forget it right after the click (touch presses
      // are judged on click) and, whatever happens, after a second, so a later Tab or focus change is never affected.
      if (timer) clearTimeout(timer);
      timer = setTimeout(rearm, 1000);
    };
    const afterClick = () => setTimeout(rearm, 0);
    document.addEventListener('pointerdown', note, true);
    document.addEventListener('click', afterClick, true);
    document.addEventListener('pointercancel', rearm, true);
    return () => {
      if (timer) clearTimeout(timer);
      document.removeEventListener('pointerdown', note, true);
      document.removeEventListener('click', afterClick, true);
      document.removeEventListener('pointercancel', rearm, true);
    };
  }, []);
  // Only a pointer press can be "the click that reopens me". A focus-outside event (Tab) must still dismiss.
  const guard = React.useCallback((event: Event) => {
    if (event.type === 'dismissableLayer.pointerDownOutside' && !wasOpen.current) event.preventDefault();
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
