// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { useState } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const copyText = vi.fn<(text: string) => Promise<boolean>>(async () => true);
vi.mock('@/lib/clipboard', () => ({ copyText: (t: string) => copyText(t) }));

import { JsonArea } from './JsonArea';

function Editable({ initial, formView }: { initial: string; formView?: boolean }) {
  const [v, setV] = useState(initial);
  return <JsonArea surfaceKey="body" title="Request body (JSON)" help="What is sent." value={v} onChange={setV} formView={formView ? <div data-testid="the-form">form</div> : undefined} />;
}

function stubStorage() {
  const data = new Map<string, string>();
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v), removeItem: (k: string) => void data.delete(k), clear: () => data.clear() },
  });
}

describe('JsonArea', () => {
  beforeEach(() => { stubStorage(); copyText.mockClear(); });

  it('shows the title and help', () => {
    render(<Editable initial={'{"a":1}'} />);
    expect(screen.getByText('Request body (JSON)')).toBeInTheDocument();
    expect(screen.getByTestId('flow-json-body-help')).toHaveTextContent('What is sent.');
  });

  it('points at the problem in plain words as you type, and clears when fixed', () => {
    render(<Editable initial={'{"a": 1}'} />);
    const box = screen.getByTestId('flow-json-body-input');
    expect(screen.queryByTestId('flow-json-body-error')).toBeNull();
    fireEvent.change(box, { target: { value: '{\n  "a": 1\n  "b": 2\n}' } });
    expect(screen.getByTestId('flow-json-body-error')).toHaveTextContent('Missing comma after line 2.');
    expect(screen.getByTestId('flow-json-body-format')).toBeDisabled();
    fireEvent.change(box, { target: { value: '{"a":1,"b":2}' } });
    expect(screen.queryByTestId('flow-json-body-error')).toBeNull();
  });

  it('Format pretty-prints', () => {
    render(<Editable initial={'{"a":[1,2]}'} />);
    fireEvent.click(screen.getByTestId('flow-json-body-format'));
    expect((screen.getByTestId('flow-json-body-input') as HTMLTextAreaElement).value).toBe('{\n  "a": [\n    1,\n    2\n  ]\n}');
  });

  it('Copy puts the text on the clipboard', async () => {
    render(<Editable initial={'{"a":1}'} />);
    fireEvent.click(screen.getByTestId('flow-json-body-copy'));
    await waitFor(() => expect(copyText).toHaveBeenCalledWith('{"a":1}'));
    expect(await screen.findByText('Copied')).toBeInTheDocument();
  });

  it('opens as the form when there is one, and remembers the switch', () => {
    const { unmount } = render(<Editable initial={'{"a":1}'} formView />);
    expect(screen.getByTestId('the-form')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('flow-json-body-toggle'));
    expect(screen.queryByTestId('the-form')).toBeNull();
    expect(screen.getByTestId('flow-json-body-input')).toBeInTheDocument();
    unmount();
    render(<Editable initial={'{"a":1}'} formView />);
    expect(screen.queryByTestId('the-form')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-json-body-toggle'));
    expect(screen.getByTestId('the-form')).toBeInTheDocument();
  });

  it('read-only: pretty prints, folds long content and has no Format or input', () => {
    const big = JSON.stringify(Object.fromEntries(Array.from({ length: 30 }, (_, i) => [`k${i}`, i])));
    render(<JsonArea surfaceKey="raw" title="Raw data" value={big} readOnly textTestId="out" />);
    expect(screen.queryByTestId('flow-json-raw-format')).toBeNull();
    expect(screen.queryByTestId('flow-json-raw-input')).toBeNull();
    expect(screen.getByTestId('out').textContent).toContain('"k29": 29');
    const more = screen.getByTestId('flow-json-raw-more');
    expect(more).toHaveTextContent('Show all 32 lines');
    fireEvent.click(more);
    expect(more).toHaveTextContent('Show less');
  });
});
