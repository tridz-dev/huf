import { forwardRef, type HTMLAttributes, type KeyboardEvent, type MouseEvent } from 'react';

/**
 * A button that is not a <button>. The phone shows every step read-only by switching off all form controls in the
 * sheet (a disabled <fieldset>), which would also switch off the tabs, the "things to finish" strip, the (i) and the
 * folded sections that people need in order to READ a step. These are not form controls, so they keep working.
 */
export const Pressable = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement> & { role?: string }>(function Pressable(
  { role = 'button', onClick, onKeyDown, ...rest },
  ref
) {
  const keys = (e: KeyboardEvent<HTMLDivElement>) => {
    onKeyDown?.(e);
    if (e.defaultPrevented) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick?.(e as unknown as MouseEvent<HTMLDivElement>);
    }
  };
  return <div ref={ref} role={role} tabIndex={0} onClick={onClick} onKeyDown={keys} {...rest} />;
});
