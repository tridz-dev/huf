// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('../__tests__/formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('../__tests__/formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('../__tests__/formTestKit')).catalogMock());
vi.mock('@/services/flow/formOptionsApi', () => ({
  listCreateDocTypes: vi.fn().mockResolvedValue([{ name: 'ToDo', label: 'To-do' }, { name: 'Note', label: 'Note' }]),
  listCreateDocFields: vi.fn().mockImplementation(async (dt: string) =>
    dt === 'Note'
      ? [{ fieldname: 'title', label: 'Title', fieldtype: 'Data', kind: 'text', required: true, options: [] }]
      : [
          { fieldname: 'description', label: 'Description', fieldtype: 'Text Editor', kind: 'longtext', required: true, options: [] },
          { fieldname: 'priority', label: 'Priority', fieldtype: 'Select', kind: 'choice', required: false, options: ['Low', 'Medium', 'High'] },
          { fieldname: 'done', label: 'Done', fieldtype: 'Check', kind: 'yesno', required: false, options: [] },
        ]
  ),
}));

import { DocCreateForm } from './DocCreateForm';
import { StateForm } from './StateForm';
import { TransformForm, startingData } from './TransformForm';
import { latest, renderForm } from '../__tests__/formTestKit';
import { buildPickerModel } from '@/lib/flow-data/model';
import { flow } from '../__tests__/formTestKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
afterEach(cleanup);

const type = (el: HTMLElement, text: string) => {
  el.textContent = text;
  fireEvent.input(el);
};

describe('TransformForm', () => {
  it('groups the operations, each with a tiny example, and shows what the chosen one does', async () => {
    renderForm(TransformForm, { type: 'transform', op: 'lower', input: {} });
    await screen.findByText('What to do');
    expect(screen.getByTestId('flow-hint-transform-example').textContent).toContain('hello world');
    expect(screen.getByTestId('flow-field-test-input.text')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Literal|\$from|Reference/);
  });

  it('text starts from the data the step before produced', () => {
    const model = buildPickerModel(flow.nodes as never, flow.edges as never, 'step', null);
    const data = startingData('lower', model);
    expect(data.text).toEqual({ $from: 'post' });
    // a list operation starts from the first list it can find
    expect(Object.keys(startingData('limit', model))).toEqual([]);
  });

  it('"Replace with" may stay empty: it removes the text', async () => {
    renderForm(TransformForm, { type: 'transform', op: 'replace', input: { text: 'a-b', find: '-' } });
    await screen.findByText('Replace with');
    expect(screen.getByText('Replace with').textContent).not.toContain('optional');
    expect(screen.getByTestId('flow-more-options-transform').dataset.state).toBe('closed');
    fireEvent.click(screen.getByTestId('flow-more-options-transform-toggle'));
    expect(screen.getByText('Replace only the first (optional)')).toBeTruthy();
  });

  it('a short list of values is rows, not JSON', async () => {
    renderForm(TransformForm, { type: 'transform', op: 'concat', input: {} });
    await screen.findByTestId('flow-field-test-input.parts');
    fireEvent.click(screen.getByTestId('flow-field-test-input.parts-add'));
    fireEvent.click(screen.getByTestId('flow-field-test-input.parts-add'));
    type(screen.getByTestId('flow-field-test-input.parts-item-0'), 'Hello');
    type(screen.getByTestId('flow-field-test-input.parts-item-1'), 'Ada');
    expect((latest.input as Record<string, unknown>).parts).toEqual(['Hello', 'Ada']);
    expect(document.body.textContent).not.toMatch(/\["a"/);
  });

  it('numbers are stored as numbers', async () => {
    renderForm(TransformForm, { type: 'transform', op: 'limit', input: {} });
    await screen.findByTestId('flow-field-test-input.count');
    type(screen.getByTestId('flow-field-test-input.count'), '5');
    expect((latest.input as Record<string, unknown>).count).toBe(5);
  });
});

describe('StateForm', () => {
  it('speaks of saving data for later, not keys and seconds', async () => {
    renderForm(StateForm, { type: 'state-set' });
    await screen.findByText('Save it under the name');
    expect(screen.getByText('What to save')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\bKey\b|seconds|2592000|ttl/i);
  });

  it('"keep it for" takes minutes, hours or days and stores seconds', async () => {
    renderForm(StateForm, { type: 'state-set', key: 'cart', value: 'x', ttl_seconds: 7200 });
    const amount = await screen.findByTestId('flow-field-test-ttl_seconds');
    expect((amount as HTMLInputElement).value).toBe('2');
    expect(screen.getByTestId('flow-field-test-ttl_seconds-unit').textContent).toContain('hours');
    fireEvent.change(amount, { target: { value: '3' } });
    expect(latest.ttl_seconds).toBe(10800);
    fireEvent.change(amount, { target: { value: '' } });
    expect(latest.ttl_seconds).toBeUndefined();
  });

  it('look up and forget ask for the name only (and a fallback for look up, folded)', async () => {
    renderForm(StateForm, { type: 'state-get' });
    await screen.findByText('Name it was saved under');
    expect(screen.queryByText('What to save')).toBeNull();
    cleanup();
    renderForm(StateForm, { type: 'state-delete' });
    await screen.findByText('Name of the saved data');
  });
});

describe('DocCreateForm', () => {
  it('picks the kind of record from the list and starts with the fields it needs', async () => {
    renderForm(DocCreateForm, { type: 'doc-create', doctype: '', fields: {} });
    const trigger = await screen.findByTestId('flow-field-test-doctype');
    await waitFor(() => expect((trigger as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(trigger);
    fireEvent.click(await screen.findByText('To-do'));
    await waitFor(() => expect(latest.doctype).toBe('ToDo'));
    await waitFor(() => expect(latest.fields).toEqual({ description: '' }));
    expect(await screen.findByText('Description')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/field_1|lowercase with underscores/);
  });

  it('a field row is asked in the way its field works: choice, yes or no, text', async () => {
    renderForm(DocCreateForm, { type: 'doc-create', doctype: 'ToDo', fields: { description: 'Call Ada', priority: 'High', done: true } });
    await screen.findByText('Priority');
    expect(screen.getByTestId('flow-field-test-fields.1.value').textContent).toContain('High');
    expect(screen.getByTestId('flow-field-test-fields.2.value')).toBeTruthy();
    type(screen.getByTestId('flow-field-test-fields.0.value'), 'Call Grace');
    expect((latest.fields as Record<string, unknown>).description).toBe('Call Grace');
  });

  it('adding a field offers the others by name and removing works', async () => {
    renderForm(DocCreateForm, { type: 'doc-create', doctype: 'ToDo', fields: { description: 'x' } });
    await screen.findByText('Description');
    await waitFor(() => expect(screen.getByTestId('flow-field-test-fields.add')).toBeTruthy());
    fireEvent.click(screen.getByTestId('flow-field-test-fields.add'));
    fireEvent.click(await screen.findByText('Priority'));
    await waitFor(() => expect(Object.keys(latest.fields as object)).toEqual(['description', 'priority']));
    fireEvent.click(screen.getByTestId('flow-field-test-fields.0.remove'));
    expect(Object.keys(latest.fields as object)).toEqual(['priority']);
  });

  it('says so when the saved kind of record is not allowed', async () => {
    renderForm(DocCreateForm, { type: 'doc-create', doctype: 'Customer', fields: {} });
    await waitFor(() => expect(screen.getByTestId('flow-hint-doc-create-doctype').textContent).toContain('not on the allowed list'));
  });
});
