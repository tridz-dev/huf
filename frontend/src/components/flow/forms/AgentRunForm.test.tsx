// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());
vi.mock('@/services/agentApi', () => ({ getAgents: vi.fn().mockResolvedValue([{ name: 'AG-1', agent_name: 'Support helper' }]) }));

import { AgentRunForm } from './AgentRunForm';
import { boxText, latest, renderForm } from './formTestKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
afterEach(cleanup);

const prompt = () => screen.getByTestId('flow-field-test-prompt');
const type = (box: HTMLElement, text: string) => {
  box.textContent = text;
  fireEvent.input(box);
};

describe('AgentRunForm', () => {
  it('asks in plain words: which agent, what to tell it, no jargon', async () => {
    renderForm(AgentRunForm, {});
    await screen.findByText('Which agent');
    expect(screen.getByText('What to tell it')).toBeTruthy();
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/Literal|\$from|Reference|Prompt\b|binding/i);
    expect(screen.getByTestId('flow-field-test-prompt-picker')).toBeTruthy();
  });

  it('typing the task is stored as the prompt', () => {
    renderForm(AgentRunForm, {});
    type(prompt(), 'Summarise this ticket');
    expect(latest.prompt).toBe('Summarise this ticket');
    expect(latest.prompt_bindings).toBeUndefined();
  });

  it('a prompt with data opens as a chip and keeps its data when more is typed', async () => {
    const stored = { prompt: 'Summarise {ticket}', prompt_bindings: { ticket: { $from: 'input.customer.name' } } };
    renderForm(AgentRunForm, stored);
    const box = prompt();
    await waitFor(() => expect(box.querySelector('[data-chip]')).toBeTruthy());
    expect(document.body.textContent).not.toContain('Data used in the prompt');
    box.appendChild(document.createTextNode(' please'));
    fireEvent.input(box);
    expect(latest.prompt).toBe('Summarise {ticket} please');
    expect(latest.prompt_bindings).toEqual(stored.prompt_bindings);
  });

  it('typed braces stay braces', () => {
    renderForm(AgentRunForm, {});
    type(prompt(), 'Reply as {json}');
    expect(latest.prompt).toBe('Reply as {{json}}');
    expect(latest.prompt_bindings).toBeUndefined();
  });

  it('choosing an agent stores its name', async () => {
    renderForm(AgentRunForm, { agent: 'AG-1' });
    await waitFor(() => expect(boxText(screen.getByTestId('flow-field-test-agent'))).toContain('Support helper'));
  });
});
