import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getWorkspaceDefaultModel, runAgentDraftTest, isEndpointUnavailable } from './agentFormApi';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/frappe-sdk', () => ({ db: {}, call: { get, post } }));

beforeEach(() => { get.mockReset(); post.mockReset(); });

describe('agentFormApi', () => {
  it('GETs default model and POSTs draft test', async () => {
    get.mockResolvedValue({ message: { provider: 'P', model: 'M' } });
    expect(await getWorkspaceDefaultModel()).toEqual({ provider: 'P', model: 'M' });
    post.mockResolvedValue({ message: { success: true } });
    await runAgentDraftTest('A', 'hi', { instructions: 'x' });
    expect(post).toHaveBeenCalledWith('huf.ai.agent.agent_form_api.run_agent_draft_test',
      { agent_name: 'A', prompt: 'hi', draft_overrides: '{"instructions":"x"}' });
  });
  it('maps a missing endpoint to a recognisable error', async () => {
    post.mockRejectedValue({ httpStatus: 404 });
    await expect(runAgentDraftTest('A', 'hi')).rejects.toSatisfy(isEndpointUnavailable);
  });
  it('passes other errors through', async () => {
    const err = new Error('boom');
    post.mockRejectedValue(err);
    await expect(runAgentDraftTest('A', 'hi')).rejects.toBe(err);
  });
});
