// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentTryPanel } from './AgentTryPanel';

const { run } = vi.hoisted(() => ({ run: vi.fn() }));
vi.mock('@/services/agentForm/agentFormApi', () => ({
  runAgentDraftTest: run,
  isEndpointUnavailable: (e: unknown) => (e as { unavailable?: boolean })?.unavailable === true,
}));

describe('AgentTryPanel', () => {
  it('is disabled with an explanation before the agent exists', () => {
    render(<AgentTryPanel agentName={undefined} getDraftOverrides={() => ({})} />);
    expect(screen.getByTestId('try-disabled')).toHaveTextContent('Create the agent first');
  });
  it('sends draft overrides and shows inspector + run link', async () => {
    run.mockResolvedValue({ success: true, response: 'Hello', agent_run_id: 'RUN-1', tool_calls: [{ tool: 'lookup' }], latency_ms: 1800, tokens: { total: 412 } });
    render(<AgentTryPanel agentName="A" getDraftOverrides={() => ({ instructions: 'draft' })} starters={['Hi there']} />);
    await userEvent.click(screen.getByRole('button', { name: 'Hi there' }));
    expect(run).toHaveBeenCalledWith('A', 'Hi there', { instructions: 'draft' });
    expect(await screen.findByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('1.8s')).toBeInTheDocument();
    expect(screen.getByText('412 tokens')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View run details' })).toHaveAttribute('href', '/executions/RUN-1');
  });
  it('maps a missing-key error to a friendly message with a Providers link and no coaching banner', async () => {
    run.mockResolvedValue({ success: false, response: null, error: 'Password not found for AI Provider AWS Bedrock api_key', agent_run_id: null, tool_calls: [], latency_ms: 5 });
    render(<AgentTryPanel agentName="A" getDraftOverrides={() => ({})} starters={['Hi']} renderBanner={(l) => (l && !l.errored ? <p>banner</p> : null)} />);
    await userEvent.click(screen.getByRole('button', { name: 'Hi' }));
    expect((await screen.findAllByText(/has no API key/)).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: 'Providers' })[0]).toHaveAttribute('href', '/providers');
    expect(screen.queryByText(/Password not found/)).toBeNull();
    expect(screen.queryByText('banner')).toBeNull();
  });
  it('degrades gracefully when the endpoint is missing', async () => {
    run.mockRejectedValue({ unavailable: true });
    render(<AgentTryPanel agentName="A" getDraftOverrides={() => ({})} starters={['Hi']} />);
    await userEvent.click(screen.getByRole('button', { name: 'Hi' }));
    expect((await screen.findAllByText(/needs a backend update/))[0]).toBeInTheDocument();
  });
});
