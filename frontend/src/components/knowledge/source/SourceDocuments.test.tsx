// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { KnowledgeInputDoc } from '@/types/knowledge.types';
import { SourceDocuments, type SourceDocumentsProps } from './SourceDocuments';

const doc = (o: Partial<KnowledgeInputDoc>) =>
  ({ name: 'a', input_type: 'File', status: 'Indexed', file_name: 'a.pdf', creation: '2026-01-01 10:00:00', ...o }) as KnowledgeInputDoc;

const base = (o: Partial<SourceDocumentsProps>): SourceDocumentsProps => ({
  knowledgeSource: 'ks',
  inputs: [],
  loading: false,
  counts: { total: 0, ready: 0, failed: 0, skipped: 0, inProgress: 0 },
  filter: 'all',
  onFilterChange: vi.fn(),
  onAddContent: vi.fn(),
  onFiles: vi.fn(),
  onRetried: vi.fn(),
  onReprocess: vi.fn(),
  onRemove: vi.fn(),
  ...o,
});

describe('SourceDocuments', () => {
  it('shows the drop zone when empty', () => {
    render(<SourceDocuments {...base({})} />);
    expect(screen.getByText('Drop files here to add them')).toBeTruthy();
    expect(screen.getByText('Connect storage')).toBeTruthy();
  });

  it('shows rows with reason and retry, plus banner when failed', () => {
    const inputs = [doc({ name: 'b', status: 'Error', file_name: 'b.pdf' }), doc({ name: 'c', file_name: 'c.pdf' })];
    render(<SourceDocuments {...base({ inputs, counts: { total: 2, ready: 1, failed: 1, skipped: 0, inProgress: 0 } })} />);
    expect(screen.getByText('b.pdf')).toBeTruthy();
    expect(screen.getByText('We could not read this file.', { exact: false })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy();
    expect(screen.getByText('1 documents could not be added.')).toBeTruthy();
  });

  it('hides the banner when nothing failed', () => {
    render(<SourceDocuments {...base({ inputs: [doc({})], counts: { total: 1, ready: 1, failed: 0, skipped: 0, inProgress: 0 } })} />);
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
