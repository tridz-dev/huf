// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentCreateCard } from './AgentCreateCard';

vi.mock('@/services/agentForm/agentFormApi', () => ({
  getWorkspaceDefaultModel: vi.fn().mockResolvedValue({ provider: 'OpenAI', model: 'gpt-x' }),
}));
vi.mock('@/services/providerApi', () => ({ getProviders: vi.fn().mockResolvedValue([]), getModels: vi.fn().mockResolvedValue([]) }));

describe('AgentCreateCard', () => {
  it('shows inline errors and a summary, and does not create', async () => {
    const onCreate = vi.fn();
    render(<AgentCreateCard onCreate={onCreate} />);
    await userEvent.click(screen.getByRole('button', { name: /create and try it/i }));
    expect(screen.getByTestId('error-summary')).toHaveTextContent('2 things need fixing');
    expect(onCreate).not.toHaveBeenCalled();
  });
  it('template fills instructions; submits with recommended model', async () => {
    const onCreate = vi.fn();
    render(<AgentCreateCard onCreate={onCreate} />);
    await waitFor(() => expect(screen.getByTestId('model-line')).toHaveTextContent('gpt-x'));
    await userEvent.click(screen.getByRole('button', { name: 'Customer support' }));
    await userEvent.click(screen.getByRole('button', { name: /create and try it/i }));
    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ agent_name: 'Customer support', provider: 'OpenAI', model: 'gpt-x', instructions: expect.stringContaining('support') }));
  });
});
