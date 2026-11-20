// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SourceToolbar } from './SourceToolbar';

const base = {
  onQueryChange: vi.fn(),
  onSubmit: vi.fn(),
  filter: 'all' as const,
  onFilterChange: vi.fn(),
  counts: { total: 5, ready: 3, failed: 2, skipped: 0, inProgress: 0 },
};

describe('SourceToolbar', () => {
  it('shows pills, hiding empty ones', () => {
    render(<SourceToolbar {...base} query="" hasDocs />);
    expect(screen.getByRole('radiogroup', { name: 'Filter by status' })).toBeTruthy();
    expect(screen.getByText('Needs attention')).toBeTruthy();
    expect(screen.queryByText('Skipped')).toBeNull();
  });
  it('hides pills while searching or with no docs', () => {
    const { rerender } = render(<SourceToolbar {...base} query="refund" hasDocs />);
    expect(screen.queryByRole('radiogroup')).toBeNull();
    rerender(<SourceToolbar {...base} query="" hasDocs={false} />);
    expect(screen.queryByRole('radiogroup')).toBeNull();
  });
});
