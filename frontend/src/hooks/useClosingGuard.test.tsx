// @vitest-environment jsdom
import * as React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { useClosingGuard, withGuard } from './useClosingGuard';

function Probe({ state, onReady }: { state: 'open' | 'closed'; onReady: (guard: (e: Event) => void) => void }) {
  const { ref, guard } = useClosingGuard<HTMLDivElement>(null);
  React.useEffect(() => { onReady(guard); }, [guard, onReady]);
  return <div ref={ref} data-state={state} data-testid="c" />;
}

afterEach(cleanup);

const press = () => document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }));

describe('ux31-03: a fading menu ignores outside clicks that began while it was fading', () => {
  it('cancels the dismissal when the click started while the content was closed (fading), even if the click itself opened it again', () => {
    let guard!: (e: Event) => void;
    const view = render(<Probe state="closed" onReady={(g) => (guard = g)} />);
    press();
    // The trigger's handler has re-rendered the content as open by the time the outside check runs.
    view.rerender(<Probe state="open" onReady={(g) => (guard = g)} />);
    const event = new Event('pointerdown', { cancelable: true });
    guard(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('lets an open menu close on an outside click', () => {
    let guard!: (e: Event) => void;
    render(<Probe state="open" onReady={(g) => (guard = g)} />);
    press();
    const event = new Event('pointerdown', { cancelable: true });
    guard(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it('runs the caller handler first and respects its preventDefault', () => {
    const seen: string[] = [];
    const handler = withGuard<Event>((e) => seen.push(e.type), () => seen.push('guard'));
    handler(new Event('x', { cancelable: true }));
    expect(seen).toEqual(['x', 'guard']);
  });
});
