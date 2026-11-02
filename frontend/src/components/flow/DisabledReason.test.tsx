// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisabledReason } from './DisabledReason';

afterEach(cleanup);

describe('DisabledReason', () => {
  it('leaves the control alone when there is no reason', () => {
    const onClick = vi.fn();
    render(<DisabledReason reason={null}><button onClick={onClick}>Run</button></DisabledReason>);
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('disabled-reason')).toBeNull();
  });

  it('keeps the control focusable, ignores clicks and offers the reason to assistive tech', async () => {
    const onClick = vi.fn();
    render(<DisabledReason reason="View only"><button disabled onClick={onClick}>Run</button></DisabledReason>);
    const button = screen.getByRole('button', { name: 'Run' });
    expect(button).not.toBeDisabled();
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(button).toHaveAccessibleDescription('View only');
    await userEvent.tab();
    expect(button).toHaveFocus();
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });
});
