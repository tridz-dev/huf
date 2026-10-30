// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());
vi.mock('@/services/providerApi', () => ({ getModels: vi.fn().mockResolvedValue([]), getProviders: vi.fn().mockResolvedValue([]) }));

import { LoopForm } from '../LoopForm';
import { RouterForm } from '../RouterForm';
import { flow, latest, renderForm, updateEdges } from './formTestKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
afterEach(cleanup);

const type = (el: HTMLElement, text: string) => {
  el.textContent = text;
  fireEvent.input(el);
};

describe('RouterForm', () => {
  it('asks a plain question first, then the paths, then the fallback, with the model folded away', async () => {
    flow.edges.push({ id: 'o1', source: 'step', target: 'end', sourceHandle: 'option', label: 'urgent', data: { route: 'option' } });
    renderForm(RouterForm, { type: 'router', prompt: '', default: 'end' });
    await screen.findByText('What should the AI decide?');
    expect(screen.getByText('Paths the AI can take')).toBeTruthy();
    expect(screen.getByText('If nothing fits, go to')).toBeTruthy();
    expect(screen.getByTestId('flow-more-options').dataset.state).toBe('closed');
    expect(document.body.textContent).not.toMatch(/Literal|\$from|arrow/);
    flow.edges.pop();
  });

  it('the question keeps data as {placeholders} in the stored text', async () => {
    renderForm(RouterForm, { type: 'router', prompt: 'Is {input.customer.name} urgent?' });
    const box = await screen.findByTestId('flow-field-test-prompt');
    await waitFor(() => expect(box.querySelector('[data-chip]')).toBeTruthy());
    box.appendChild(document.createTextNode(' Answer in one word.'));
    fireEvent.input(box);
    expect(latest.prompt).toBe('Is {input.customer.name} urgent? Answer in one word.');
  });

  it('typing the question stores plain text', async () => {
    renderForm(RouterForm, { type: 'router' });
    type(await screen.findByTestId('flow-field-test-prompt'), 'Is this urgent or routine?');
    expect(latest.prompt).toBe('Is this urgent or routine?');
  });

  it('a path is named in a full-width box and says where it goes', async () => {
    flow.edges.push({ id: 'o1', source: 'step', target: 'end', sourceHandle: 'option', label: '', data: { route: 'option' } });
    renderForm(RouterForm, { type: 'router', prompt: 'x' });
    const name = await screen.findByTestId('flow-router-path-label-end');
    fireEvent.change(name, { target: { value: 'urgent' } });
    expect(updateEdges).toHaveBeenCalled();
    expect(screen.getByTestId('flow-router-path-goes-end').textContent).toContain('goes to End');
    flow.edges.pop();
  });
});

describe('LoopForm', () => {
  it('the list and the result are picked, never typed, and read as step names', async () => {
    flow.edges.push({ id: 'b1', source: 'step', target: 'post', sourceHandle: 'body', data: { route: 'body' } });
    renderForm(LoopForm, { type: 'foreach', items: { $from: 'input.items' }, collect: { $from: 'post' }, max_iterations: 10, on_item_error: 'fail' });
    const items = await screen.findByTestId('flow-field-test-items');
    const collect = screen.getByTestId('flow-field-test-collect');
    await waitFor(() => expect(collect.querySelector('[data-chip]')).toBeTruthy());
    expect(collect.textContent).toContain('Call a web address');
    expect(collect.textContent).not.toMatch(/\bpost\b|n_http/);
    expect(items.querySelector('[data-chip]')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/input\.items|Literal/);
    // typing does nothing: what is stored is a reference
    const before = JSON.stringify(latest);
    fireEvent.keyDown(items, { key: 'a' });
    expect(JSON.stringify(latest)).toBe(before);
    flow.edges.pop();
  });

  it('the safety limit and what happens on a failure are folded away, with plain choices', async () => {
    renderForm(LoopForm, { type: 'foreach', max_iterations: 10, on_item_error: 'skip' });
    await screen.findByText('List to go through');
    expect(screen.getByTestId('flow-more-options-loop').dataset.state).toBe('closed');
  });

  it('opens the folded options when something there is missing', async () => {
    renderForm(LoopForm, { type: 'foreach' });
    await screen.findByText('List to go through');
    expect(screen.getByTestId('flow-more-options-loop').dataset.state).toBe('open');
    expect(screen.getByText('If one item fails')).toBeTruthy();
  });

  it('the number of items is stored as a number', async () => {
    renderForm(LoopForm, { type: 'foreach' });
    fireEvent.change(await screen.findByTestId('flow-field-test-max_iterations'), { target: { value: '25' } });
    expect(latest.max_iterations).toBe(25);
  });
});
