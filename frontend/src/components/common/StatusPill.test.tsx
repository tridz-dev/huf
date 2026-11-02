// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { flowStatusKind, STATUS_SPECS, StatusPill, statusLabel } from './StatusPill';

describe('StatusPill', () => {
  it('uses the one status vocabulary, in sentence case', () => {
    expect(statusLabel('live')).toBe('Live');
    expect(statusLabel('has_problems')).toBe('Has problems');
    expect(statusLabel('waiting_approval')).toBe('Waiting for approval');
    for (const spec of Object.values(STATUS_SPECS)) {
      expect(spec.label).not.toBe(spec.label.toUpperCase());
    }
  });

  it('maps stored flow status to the words people read', () => {
    expect(flowStatusKind('active')).toBe('live');
    expect(flowStatusKind('draft', 3)).toBe('draft');
    expect(flowStatusKind('active', 2)).toBe('has_problems');
    expect(flowStatusKind('paused')).toBe('archived');
  });

  it('renders the word and a status hook', () => {
    render(<StatusPill kind="live" />);
    const pill = screen.getByTestId('status-pill-live');
    expect(pill.textContent).toBe('Live');
    expect(pill.getAttribute('data-status')).toBe('live');
  });
});
