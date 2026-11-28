// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { KnowledgeInputDoc } from '@/types/knowledge.types';
import { DocumentDetailSheet } from '../DocumentDetailSheet';
import { IndexedText } from './IndexedText';
import { getInputChunks } from './inputsApi';

vi.mock('./inputsApi', () => ({ getInputChunks: vi.fn(), bulkDeleteInputs: vi.fn(), CHUNKS_PAGE_SIZE: 10 }));

const page = (start: number, total: number, n: number) => ({
  supported: true,
  total,
  start,
  limit: 2,
  chunks: Array.from({ length: n }, (_, i) => ({ index: start + i, text: `text ${start + i}`, page: i === 0 ? 3 : null })),
});

beforeEach(() => {
  vi.mocked(getInputChunks).mockReset();
});

describe('IndexedText', () => {
  it('shows the first page and pages forward', async () => {
    vi.mocked(getInputChunks).mockResolvedValueOnce(page(0, 3, 2)).mockResolvedValueOnce(page(2, 3, 1));
    render(<IndexedText knowledgeInput="A" version="v" indexed />);
    await waitFor(() => expect(screen.getAllByTestId('indexed-chunk')).toHaveLength(2));
    expect(screen.getByText(/Page 3/)).toBeTruthy();
    expect(screen.getByText(/1-2 of 3 sections/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(screen.getByText('text 2')).toBeTruthy());
    expect(getInputChunks).toHaveBeenLastCalledWith('A', 2);
    expect((screen.getByRole('button', { name: 'Next' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('says so when the backend cannot list its chunks', async () => {
    vi.mocked(getInputChunks).mockResolvedValue({ supported: false, chunks: [], total: 0, start: 0, limit: 10 });
    render(<IndexedText knowledgeInput="A" version="v" indexed />);
    await waitFor(() => expect(screen.getByText(/cannot show the indexed text/)).toBeTruthy());
  });

  it('does not fetch before the input is indexed', () => {
    render(<IndexedText knowledgeInput="A" version="v" indexed={false} />);
    expect(getInputChunks).not.toHaveBeenCalled();
    expect(screen.getByText(/Nothing is indexed yet/)).toBeTruthy();
  });

  it('shows the server error', async () => {
    vi.mocked(getInputChunks).mockImplementation(() => Promise.reject(new Error('Not permitted to read this document')));
    render(<IndexedText knowledgeInput="A" version="v" indexed />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
  });
});

describe('DocumentDetailSheet original', () => {
  const input = (o: Partial<KnowledgeInputDoc>) =>
    ({ name: 'KI-1', input_type: 'File', status: 'Indexed', creation: '2026-01-01 10:00:00', ...o }) as KnowledgeInputDoc;

  it('offers the original file and the indexed text', async () => {
    vi.mocked(getInputChunks).mockResolvedValue(page(0, 1, 1));
    render(<DocumentDetailSheet input={input({ file: '/private/files/a.pdf', file_name: 'a.pdf' })} onOpenChange={vi.fn()} />);
    expect(screen.getByRole('link', { name: /Download original/ }).getAttribute('href')).toBe('/private/files/a.pdf');
    await waitFor(() => expect(screen.getByTestId('indexed-chunk')).toBeTruthy());
  });

  it('links a URL input and downloads a Text input', () => {
    vi.mocked(getInputChunks).mockResolvedValue(page(0, 1, 1));
    const { unmount } = render(<DocumentDetailSheet input={input({ input_type: 'URL', url: 'https://example.com/x' })} onOpenChange={vi.fn()} />);
    expect(screen.getByRole('link', { name: /Open page/ }).getAttribute('href')).toBe('https://example.com/x');
    unmount();
    render(<DocumentDetailSheet input={input({ input_type: 'Text', text: 'hello world' })} onOpenChange={vi.fn()} />);
    expect(screen.getByRole('link', { name: /Download original/ }).getAttribute('href')).toContain('hello%20world');
  });

  it('refuses a non-http URL', () => {
    vi.mocked(getInputChunks).mockResolvedValue(page(0, 1, 1));
    render(<DocumentDetailSheet input={input({ input_type: 'URL', url: 'javascript:alert(1)' })} onOpenChange={vi.fn()} />);
    expect(screen.queryByRole('link', { name: /Open page/ })).toBeNull();
  });
});
