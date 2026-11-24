// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('./formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('./formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('./formTestKit')).catalogMock());
vi.mock('@/services/flow/triggerApi', () => ({ listTriggerDoctypes: vi.fn().mockResolvedValue([{ name: 'ToDo', label: 'To-do' }]) }));

import { SchemaNodeForm } from '../SchemaNodeForm';
import { latest, renderForm } from './formTestKit';
import { appActionOptions, setAppNodeTypes } from '@/lib/flow-graph/appNodeTypes';
import { validateNode } from '@/lib/flow-graph/flowValidation';
import { defaultActionConfig } from '@/lib/flow-history/actionDefaults';
import type { AppNodeType } from '@/services/flow/nodeTypesApi';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;

const nodeType = (schema: AppNodeType['config_schema'], extra: Partial<AppNodeType> = {}): AppNodeType => ({
  type: 'acme.ship', label: 'Ship order', category: 'data', icon: 'Truck', description: 'Ships an order.', app: 'acme', config_schema: schema, ...extra,
});
const open = (schema: AppNodeType['config_schema'], cfg: Record<string, unknown> = {}) => {
  setAppNodeTypes([nodeType(schema)]);
  return renderForm(SchemaNodeForm, { type: 'unknown', backend_type: 'acme.ship', ...cfg });
};
const field = (name: string) => screen.getByTestId(`flow-field-test-${name}`);

beforeEach(() => setAppNodeTypes(null));
afterEach(cleanup);

describe('SchemaNodeForm', () => {
  it('names the app and shows a title and description per setting', () => {
    open({ type: 'object', properties: { note: { type: 'string', title: 'Note', description: 'Shown to the courier.' } } });
    expect(screen.getByText('Added by acme')).toBeTruthy();
    expect(screen.getByText('Note')).toBeTruthy();
    expect(screen.getByText('Shown to the courier.')).toBeTruthy();
  });

  it('says so when the step has no settings', () => {
    open({ type: 'object', properties: {} });
    expect(screen.getByText('This step has no settings.')).toBeTruthy();
  });

  it('shows the not-installed card when the type is gone', () => {
    setAppNodeTypes([]);
    renderForm(SchemaNodeForm, { type: 'unknown', backend_type: 'gone.step' });
    expect(screen.getByTestId('flow-schema-missing').textContent).toContain('not installed');
  });

  it('string: writes text, and removes the key when emptied', () => {
    open({ type: 'object', properties: { note: { type: 'string', title: 'Note' } } });
    fireEvent.change(field('note'), { target: { value: 'hi' } });
    expect(latest.note).toBe('hi');
    fireEvent.change(field('note'), { target: { value: '' } });
    expect('note' in latest).toBe(false);
  });

  it('number: stores a number', () => {
    open({ type: 'object', properties: { qty: { type: 'integer', title: 'Quantity' } } });
    fireEvent.change(field('qty'), { target: { value: '3' } });
    expect(latest.qty).toBe(3);
  });

  it('boolean: stores true and false', () => {
    open({ type: 'object', properties: { rush: { type: 'boolean', title: 'Rush' } } });
    fireEvent.click(field('rush'));
    expect(latest.rush).toBe(true);
    fireEvent.click(field('rush'));
    expect(latest.rush).toBe(false);
  });

  it('enum: offers the choices as a select', () => {
    open({ type: 'object', properties: { speed: { type: 'string', title: 'Speed', enum: ['slow', 'fast'] } } }, { speed: 'slow' });
    expect(field('speed').getAttribute('role')).toBe('combobox');
  });

  it('array of string: splits on commas', () => {
    open({ type: 'object', properties: { tags: { type: 'array', title: 'Tags', items: { type: 'string' } } } });
    fireEvent.change(field('tags'), { target: { value: 'a, b ,c' } });
    expect(latest.tags).toEqual(['a', 'b', 'c']);
  });

  it('object: nests its properties and writes them under the parent key', () => {
    open({ type: 'object', properties: { address: { type: 'object', title: 'Address', properties: { city: { type: 'string', title: 'City' } } } } });
    fireEvent.change(field('address.city'), { target: { value: 'Oslo' } });
    expect(latest.address).toEqual({ city: 'Oslo' });
  });

  it('x-huf-widget data-ref: uses the data input', () => {
    open({ type: 'object', properties: { who: { type: 'string', title: 'Who', 'x-huf-widget': 'data-ref' } } });
    expect(field('who')).toBeTruthy();
    expect(screen.getByTestId('flow-field-test-who-picker')).toBeTruthy();
  });

  it('x-huf-widget template: stores text typed into the data box', () => {
    open({ type: 'object', properties: { body: { type: 'string', title: 'Body', 'x-huf-widget': 'template' } } });
    const box = field('body');
    box.textContent = 'Hello';
    fireEvent.input(box);
    expect(latest.body).toBe('Hello');
  });

  it('x-huf-widget doctype: picks from the document types', async () => {
    open({ type: 'object', properties: { dt: { type: 'string', title: 'Record type', 'x-huf-widget': 'doctype' } } });
    await waitFor(() => expect(field('dt')).toBeTruthy());
  });
});

describe('app steps in the palette and publish check', () => {
  it('appActionOptions maps the catalog to palette entries, unknown categories under Apps', () => {
    const opts = appActionOptions([nodeType({}), nodeType({}, { type: 'acme.x', category: 'weird' })]);
    expect(opts[0]).toMatchObject({ id: 'acme.ship', name: 'Ship order', category: 'data', icon: 'Truck' });
    expect(opts[1].category).toBe('apps');
  });

  it('a new app step starts as an unknown-typed config carrying its type id', () => {
    setAppNodeTypes([nodeType({})]);
    expect(defaultActionConfig('acme.ship')).toEqual({ type: 'unknown', backend_type: 'acme.ship' });
  });

  it('blocks publish until schema-required settings are filled, with "Fill in {title}."', () => {
    setAppNodeTypes([nodeType({ type: 'object', required: ['note'], properties: { note: { type: 'string', title: 'Note' } } })]);
    const node = (cfg: Record<string, unknown>) => ({ id: 'n', data: { label: 'Ship order', nodeType: 'action' as const, actionConfig: { type: 'unknown', backend_type: 'acme.ship', ...cfg } } });
    const bad = validateNode(node({}) as never, []);
    expect(bad.map((i) => [i.field, i.message])).toEqual([['note', 'Fill in Note.']]);
    expect(validateNode(node({ note: 'x' }) as never, [])).toEqual([]);
  });
});
