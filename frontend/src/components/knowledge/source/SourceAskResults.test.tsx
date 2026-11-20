// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
vi.mock('@/services/knowledgeApi', () => ({ testSearch: vi.fn() }));
import { SourceAskResults } from './SourceAskResults';

const base = { asked: 'refund policy', searching: false, error: null, blocked: null, onClear: vi.fn(), onOpenDocument: vi.fn() };

describe('SourceAskResults', () => {
  it('renders result cards with marked terms', () => {
    const results = [
      { chunk_id: 'a', input_title: 'Policy.pdf', text: 'Our refund policy is simple.', score: 0.9, metadata: { page: 2 } },
      { chunk_id: 'b', title: 'FAQ', text: 'Other text', score: 0.2 },
    ];
    const { container } = render(<SourceAskResults {...base} results={results} />);
    expect(screen.getAllByTestId('result-card')).toHaveLength(2);
    expect(container.querySelectorAll('mark').length).toBeGreaterThan(0);
    expect(screen.getByText('These are the passages your agents would read.')).toBeTruthy();
    expect(screen.getByText('page 2')).toBeTruthy();
  });
  it('shows the empty state', () => {
    render(<SourceAskResults {...base} results={[]} />);
    expect(screen.getByText('Nothing matched. Try different words.')).toBeTruthy();
  });
  it('shows an error', () => {
    render(<SourceAskResults {...base} results={null} error="Boom" />);
    expect(screen.getByText('Boom')).toBeTruthy();
  });
});
