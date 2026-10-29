// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Pressable } from './Pressable';

describe('Pressable', () => {
  it('works inside a disabled fieldset (the phone read-only sheet) by click and by keyboard', () => {
    const onClick = vi.fn();
    render(
      <fieldset disabled>
        <Pressable onClick={onClick}>Open</Pressable>
        <button>real button</button>
      </fieldset>
    );
    const el = screen.getByRole('button', { name: 'Open' });
    fireEvent.click(el);
    fireEvent.keyDown(el, { key: 'Enter' });
    fireEvent.keyDown(el, { key: ' ' });
    expect(onClick).toHaveBeenCalledTimes(3);
    expect((screen.getByText('real button') as HTMLButtonElement).disabled).toBe(true);
  });

  it('is a tab when asked to be', () => {
    render(<Pressable role="tab" aria-selected>Setup</Pressable>);
    expect(screen.getByRole('tab', { name: 'Setup' }).getAttribute('tabindex')).toBe('0');
  });
});
