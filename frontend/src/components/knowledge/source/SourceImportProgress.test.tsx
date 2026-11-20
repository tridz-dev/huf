// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { SourceImportProgress, importSummary } from './SourceImportProgress';

const getStatus = vi.fn();
vi.mock('@/services/knowledgeApi', () => ({
  ACTIVE_INGESTION_STATUSES: ['Queued', 'Scanning', 'Running'],
  getIngestionStatus: (...a: unknown[]) => getStatus(...a),
  listIngestions: vi.fn(),
  cancelIngestion: vi.fn(),
}));

const make = (status: string, total_items: number, counts: Record<string, number>) => ({
  ingestion: { name: 'I1', status, total_items, source_config: { bucket: 'b' } },
  counts: { indexed: 0, error: 0, skipped: 0, total: 0, ...counts },
  progress: 0,
});

describe('SourceImportProgress', () => {
  beforeEach(() => getStatus.mockReset());

  it('scanning shows indeterminate found-so-far from total_items', async () => {
    getStatus.mockResolvedValue(make('Scanning', 412, {}));
    const onProgress = vi.fn();
    render(<SourceImportProgress ingestion="I1" onFinished={vi.fn()} onViewDetails={vi.fn()} onProgress={onProgress} />);
    expect(await screen.findByText(/412 files found so far/)).toBeTruthy();
    expect(screen.getByTestId('progress-row').dataset.mode).toBe('indeterminate');
    await waitFor(() => expect(onProgress).toHaveBeenCalledWith({ label: 'Finding files', done: 412, total: 0 }));
  });

  it('running shows determinate progress', async () => {
    getStatus.mockResolvedValue(make('Running', 30, { total: 30, indexed: 10 }));
    render(<SourceImportProgress ingestion="I1" onFinished={vi.fn()} onViewDetails={vi.fn()} />);
    expect(await screen.findByText(/10 of 30/)).toBeTruthy();
    expect(screen.getByTestId('progress-row').dataset.mode).toBe('determinate');
  });

  it('importSummary is null when finished', () => {
    expect(importSummary(make('Completed', 3, { total: 3 }) as never)).toBeNull();
  });
});
