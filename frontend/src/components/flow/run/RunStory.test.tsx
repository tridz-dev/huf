// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { RunStepCard } from './RunStepCard';
import { RunStatusBanner } from './RunStatusBanner';
import { OutcomeChip, RunStatusPill } from './RunStatusBits';
import type { StoryStep } from '@/lib/flow-run/story/runSteps';
import type { FlowRunDetail } from '@/services/flowApi';

const base: StoryStep = { id: 's1', type: 'tool.call', title: 'Add rows', phrase: 'The tool did not work', status: 'failed', output: undefined, hideOutput: true, reason: 'Google Sheets is not connected.' };
const card = (step: StoryStep, canManage = true, onOpenStep = vi.fn()) =>
  render(
    <MemoryRouter>
      <ol><RunStepCard step={step} names={{}} titleOf={() => null} toolIdOf={() => undefined} canManage={canManage} onOpenStep={onOpenStep} /></ol>
    </MemoryRouter>,
  );

describe('failed step card', () => {
  it('has exactly one error with Fix this step and Connect', () => {
    const open = vi.fn();
    card(base, true, open);
    expect(screen.getAllByTestId('flow-run-error')).toHaveLength(1);
    expect(screen.getByTestId('flow-run-step-error-s1')).toHaveTextContent('Google Sheets is not connected.');
    expect(screen.getByTestId('flow-run-step-error-s1').className).not.toMatch(/font-mono/);
    expect(screen.getByTestId('flow-run-step-connect-s1')).toHaveTextContent('Connect Google Sheets');
    fireEvent.click(screen.getByTestId('flow-run-fix-s1'));
    expect(open).toHaveBeenCalledWith('s1');
    expect(screen.queryByText(/Failed at step/)).toBeNull();
  });

  it('read-only people can open the step but are not offered the connection', () => {
    card(base, false);
    expect(screen.getByTestId('flow-run-fix-s1')).toHaveTextContent('Open this step');
    expect(screen.queryByTestId('flow-run-step-connect-s1')).toBeNull();
  });
});

describe('loop card', () => {
  it('says how many iterations and opens to one line per round', () => {
    const loop: StoryStep = {
      id: 'l', type: 'foreach', title: 'Each name', phrase: 'Went through each item', status: 'done', output: {}, hideOutput: true,
      iterations: { count: 2, results: ['A', 'B'] },
      children: [{ id: 'b', type: 'transform', title: 'Shout', phrase: 'Changed the data', status: 'done', output: 'B' }],
    };
    card(loop);
    expect(screen.getByTestId('flow-run-iterations-toggle-l')).toHaveTextContent('2 iterations');
    expect(screen.getByTestId('flow-run-children-l')).toBeInTheDocument();
    expect(screen.queryByTestId('flow-run-iterations-list-l')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-run-iterations-toggle-l'));
    expect(screen.getByTestId('flow-run-iteration-l-2')).toHaveTextContent('Round 2');
  });
});

const run = (over: Partial<FlowRunDetail>): FlowRunDetail => ({
  flow_run_id: 'r', flow_id: 'f', flow_name: 'Orders', flow_version: 1, mode: 'Normal', status: 'Running', trigger_type: 'Manual', current_node_id: '', hop_count: 0,
  context_json: {}, waiting: {}, node_labels: {}, last_error: null, last_agent_run: null, started_at: '2026-10-29T17:00:00Z', completed_at: null,
  stale: true, can_mark_failed: true, stale_after_minutes: 15, modified_at: new Date(Date.now() - 2 * 3600_000 - 60_000).toISOString(), ...over,
});

describe('run banners', () => {
  it('a stuck run says for how long and offers a destructive Stop run with a confirm', () => {
    const stop = vi.fn();
    render(<RunStatusBanner run={run({})} canManage onStop={stop} onCancel={vi.fn()} />);
    expect(screen.getByTestId('flow-run-stuck-for')).toHaveTextContent('2 hours');
    fireEvent.click(screen.getByTestId('flow-run-mark-failed'));
    expect(screen.getByText('Stop this run?')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('flow-run-mark-failed-confirm'));
    expect(stop).toHaveBeenCalled();
  });

  it('only a system manager sees Stop run; others are told who can', () => {
    render(<RunStatusBanner run={run({ can_mark_failed: false })} canManage onStop={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByTestId('flow-run-mark-failed')).toBeNull();
    expect(screen.getByTestId('flow-run-stale')).toHaveTextContent('A system manager can stop it');
  });

  it('a queued run offers Cancel run to editors only', () => {
    const cancel = vi.fn();
    const queued = run({ status: 'Queued', stale: false });
    const { unmount } = render(<RunStatusBanner run={queued} canManage onStop={vi.fn()} onCancel={cancel} />);
    fireEvent.click(screen.getByTestId('flow-run-cancel'));
    fireEvent.click(screen.getByTestId('flow-run-mark-failed-confirm'));
    expect(cancel).toHaveBeenCalled();
    unmount();
    render(<RunStatusBanner run={queued} canManage={false} onStop={vi.fn()} onCancel={cancel} />);
    expect(screen.queryByTestId('flow-run-cancel')).toBeNull();
  });
});

describe('status bits', () => {
  it('uses the one status set: red Failed, never upper case; outcome chip keeps its tone', () => {
    render(<><RunStatusPill status="Failed" /><OutcomeChip outcome={{ label: 'Rejected', tone: 'bad' }} /></>);
    expect(screen.getByTestId('flow-run-status')).toHaveTextContent('Failed');
    expect(screen.getByTestId('flow-run-status').className).toMatch(/danger|destructive|red/);
    expect(screen.getByTestId('flow-run-outcome')).toHaveAttribute('data-tone', 'bad');
  });
});
