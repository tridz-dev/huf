// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { SourceFrame, type SourceFrameProps } from './SourceFrame';

const counts = (o: Partial<SourceFrameProps['counts']> = {}) => ({ total: 5, ready: 5, failed: 0, skipped: 0, inProgress: 0, ...o });

function Host(p: Partial<SourceFrameProps>) {
  const form = useForm<any>({ defaultValues: { source_name: 'Docs' } });
  return (
    <MemoryRouter>
      <SourceFrame
        form={form}
        knowledgeSource="KS-1"
        disabled={false}
        rebuilding={false}
        counts={counts()}
        health={{ key: 'ready', label: 'Ready', hint: '' }}
        importing={null}
        onAddContent={vi.fn()}
        onOpenSettings={vi.fn()}
        onOpenHistory={vi.fn()}
        onRebuildIndex={vi.fn()}
        onToggleDisabled={vi.fn()}
        onReview={vi.fn()}
        onConnectAgent={vi.fn()}
        {...p}
      >
        <div>body</div>
      </SourceFrame>
    </MemoryRouter>
  );
}
const text = () => screen.getByTestId('status-sentence').textContent;

describe('SourceFrame status sentence', () => {
  it('shows ready with agents', () => {
    render(<Host agents={['A', 'B']} />);
    expect(text()).toContain('Ready');
    expect(text()).toContain('5 documents');
    expect(text()).toContain('used by 2 agents');
    expect(screen.getByTestId('add-content')).toBeTruthy();
  });
  it('offers Connect to an agent when ready with no agents', () => {
    const onConnectAgent = vi.fn();
    render(<Host onConnectAgent={onConnectAgent} />);
    fireEvent.click(screen.getByText('Connect to an agent'));
    expect(onConnectAgent).toHaveBeenCalled();
  });
  it('attention beats importing and disabled', () => {
    render(<Host counts={counts({ failed: 3 })} disabled importing={{ label: 'Importing', done: 1, total: 4 }} />);
    expect(text()).toContain('3 documents need attention');
    expect(screen.getByText('Review')).toBeTruthy();
  });
  it('importing beats disabled', () => {
    render(<Host disabled importing={{ label: 'Importing', done: 2, total: 0 }} />);
    expect(text()).toContain('2 found so far');
  });
  it('shows N of M while running', () => {
    render(<Host importing={{ label: 'Importing', done: 25, total: 350 }} />);
    expect(text()).toContain('25 of 350');
  });
  it('disabled, then empty', () => {
    const { unmount } = render(<Host disabled />);
    expect(text()).toContain('Turned off');
    unmount();
    render(<Host counts={counts({ total: 0, ready: 0 })} />);
    expect(text()).toContain('No documents yet');
  });
});
