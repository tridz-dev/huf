// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryCard } from './MemoryCard';
import type { MemoryRecord } from '@/types/memory';

const record = (over: Partial<MemoryRecord> = {}): MemoryRecord => ({
  name: 'MEM-1', title: 'Employee list', record_type: 'Fact', scope_type: 'User', scope_key: 'a@example.com',
  visibility: 'Private', status: 'Active', summary_text: 'Vaishna, Shahzad', confidence: 0.8, importance_score: 5,
  tags: '', agent: 'Helper', modified: '2026-01-01 10:00:00', ...over,
});

describe('MemoryCard', () => {
  it('shows who a user-scoped memory belongs to, its agent and its status', () => {
    render(<MemoryCard memory={record()} onArchive={() => {}} />);
    expect(screen.getByTestId('memory-scope')).toHaveTextContent('Private to a@example.com · Helper');
    expect(screen.getByTestId('memory-status')).toHaveTextContent('Active');
  });

  it('shows other scopes by type and key', () => {
    render(<MemoryCard memory={record({ scope_type: 'Agent', scope_key: 'Helper', status: 'Draft' })} onArchive={() => {}} />);
    expect(screen.getByTestId('memory-scope')).toHaveTextContent('Agent · Helper');
    expect(screen.getByTestId('memory-status')).toHaveTextContent('Draft');
  });
});
