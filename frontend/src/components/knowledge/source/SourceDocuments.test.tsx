// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { KnowledgeInputDoc } from '@/types/knowledge.types';
import { SourceDocuments, dropZoneCopy, type SourceDocumentsProps } from './SourceDocuments';
import { bulkDeleteInputs } from './inputsApi';

vi.mock('./inputsApi', () => ({
  bulkDeleteInputs: vi.fn(),
  getInputChunks: vi.fn(() => new Promise(() => undefined)),
  CHUNKS_PAGE_SIZE: 10,
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

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

  it('builds the drop zone copy from import options', () => {
    const c = dropZoneCopy({ allowed_extensions: ['.pdf', 'TXT'], max_file_mb: 25 } as any);
    expect(c.accept).toBe('.pdf,.txt');
    expect(c.hint).toBe('PDF, TXT. Up to 25 MB each.');
    expect(dropZoneCopy(null)).toEqual({});
  });

  describe('bulk delete', () => {
    const three = [doc({ name: 'a', file_name: 'a.pdf' }), doc({ name: 'b', file_name: 'b.pdf' }), doc({ name: 'c', file_name: 'c.pdf' })];
    const counts = { total: 3, ready: 3, failed: 0, skipped: 0, inProgress: 0 };

    it('selects rows and deletes them after confirmation, refreshing once', async () => {
      vi.mocked(bulkDeleteInputs).mockResolvedValue({ deleted: ['a', 'b'], failed: [] });
      const onBulkDeleted = vi.fn();
      render(<SourceDocuments {...base({ inputs: three, counts, onBulkDeleted })} />);
      fireEvent.click(screen.getByRole('checkbox', { name: 'Select a.pdf' }));
      fireEvent.click(screen.getByRole('checkbox', { name: 'Select b.pdf' }));
      expect(screen.getByRole('status').textContent).toContain('2 documents selected');
      fireEvent.click(screen.getByRole('button', { name: /Delete/ }));
      expect(screen.getByText('Delete 2 documents?')).toBeTruthy();
      expect(bulkDeleteInputs).not.toHaveBeenCalled();
      fireEvent.click(screen.getAllByRole('button', { name: 'Delete' }).at(-1)!);
      await waitFor(() => expect(bulkDeleteInputs).toHaveBeenCalledWith('ks', ['a', 'b']));
      await waitFor(() => expect(onBulkDeleted).toHaveBeenCalledTimes(1));
    });

    it('select all picks every visible row', () => {
      render(<SourceDocuments {...base({ inputs: three, counts, onBulkDeleted: vi.fn() })} />);
      fireEvent.click(screen.getByRole('checkbox', { name: 'Select all documents' }));
      expect(screen.getByRole('status').textContent).toContain('3 documents selected');
    });

    it('clicking a checkbox does not open the detail sheet', () => {
      render(<SourceDocuments {...base({ inputs: three, counts, onBulkDeleted: vi.fn() })} />);
      fireEvent.click(screen.getByRole('checkbox', { name: 'Select a.pdf' }));
      expect(screen.queryByTestId('document-detail')).toBeNull();
    });

    it('shows no checkboxes without a bulk handler', () => {
      render(<SourceDocuments {...base({ inputs: three, counts })} />);
      expect(screen.queryByRole('checkbox')).toBeNull();
    });
  });
});
