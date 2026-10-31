// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { FieldError } from '../forms/formKit';
import { getFrameState, requestFocus, resetFrame, revealAllIssues } from './frameStore';

function Field({ message = 'Choose an agent.' }: { message?: string }) {
  return (
    <div>
      <div>
        <input aria-label="agent" data-testid="flow-field-agent.run-agent" />
      </div>
      <FieldError nodeId="n1" kind="agent.run" field="agent" message={message} />
      <button>elsewhere</button>
    </div>
  );
}

afterEach(() => {
  cleanup();
  act(() => resetFrame());
});

describe('required-field messages', () => {
  it('stay hidden on a form nobody has touched', () => {
    render(<Field />);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('appear once the person has been in the field and left it', () => {
    render(<Field />);
    const input = screen.getByLabelText('agent');
    input.focus();
    expect(screen.queryByRole('alert')).toBeNull();
    fireEvent.focusOut(input.parentElement as HTMLElement, { relatedTarget: screen.getByText('elsewhere') });
    expect(screen.getByRole('alert').textContent).toBe('Choose an agent.');
  });

  it('appear for every field after a publish or save attempt', () => {
    render(<Field />);
    act(() => revealAllIssues());
    expect(screen.getByRole('alert')).toBeTruthy();
  });

  it('appear for one step when the checklist sends the person to it', () => {
    render(<Field />);
    act(() => requestFocus('n1', 'agent'));
    expect(screen.getByRole('alert')).toBeTruthy();
    expect(getFrameState().focusRequest?.field).toBe('agent');
  });

  it('show nothing when there is nothing to say', () => {
    render(<Field message="" />);
    act(() => revealAllIssues());
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
