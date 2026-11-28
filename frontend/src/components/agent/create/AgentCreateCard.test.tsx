// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
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

describe('AgentCreateCard name field', () => {
  it('disables autofill and shows an inline duplicate-name error', () => {
    render(<AgentCreateCard onCreate={vi.fn()} error="Agent with this name already exists" />);
    expect(screen.getByLabelText(/^name/i)).toHaveAttribute('autocomplete', 'off');
    expect(screen.getByText(/name is already used/i)).toBeInTheDocument();
  });
});

describe('AgentCreateCard examples', () => {
  it('shows lead, 4 featured chips plus More examples, and the placeholder', () => {
    render(<AgentCreateCard onCreate={vi.fn()} />);
    expect(screen.getByText('Or start from an example:')).toBeInTheDocument();
    const group = screen.getByRole('group', { name: 'Or start from an example:' });
    expect(within(group).getAllByRole('button')).toHaveLength(5);
    expect(within(group).getByRole('button', { name: 'More examples…' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Describe what this agent/).getAttribute('placeholder')).toContain('Orders table');
  });
  it('gallery pick of a non-featured example fills fields and submits', async () => {
    const onCreate = vi.fn();
    render(<AgentCreateCard onCreate={onCreate} />);
    await userEvent.click(screen.getByRole('button', { name: 'More examples…' }));
    await userEvent.type(screen.getByLabelText('Search examples'), 'invoice remind');
    await userEvent.click(screen.getByText('Invoice reminders'));
    expect((screen.getByPlaceholderText(/Describe what this agent/) as HTMLTextAreaElement).value).toContain('Invoices table');
    expect(screen.getByLabelText(/^name/i)).toHaveValue('Invoice reminders');
    await userEvent.click(screen.getByRole('button', { name: /create and try it/i }));
    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ agent_name: 'Invoice reminders', instructions: expect.stringContaining('Invoices table') }));
  });
});
