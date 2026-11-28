// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('../__tests__/formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('../__tests__/formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('../__tests__/formTestKit')).catalogMock());
vi.mock('@/services/flow/formOptionsApi', () => ({
  listCreateDocTypes: vi.fn().mockResolvedValue([{ name: 'ToDo', label: 'To-do' }]),
  listCreateDocFields: vi.fn().mockResolvedValue([]),
}));

import { MemberSetForm } from './MemberSetForm';
import { DocUpdateForm } from './DocUpdateForm';
import { latest, renderForm } from '../__tests__/formTestKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
afterEach(cleanup);

describe('rows added to a step that stores {} for "none"', () => {
  it('Remember for this person: Add a value adds a row that stays', async () => {
    renderForm(MemberSetForm, { type: 'member-set', vars: {} });
    fireEvent.click(await screen.findByTestId('flow-field-test-vars-add'));
    expect(screen.getByTestId('flow-field-test-vars-row-0')).toBeTruthy();
    fireEvent.change(screen.getByTestId('flow-field-test-vars-key-0'), { target: { value: 'plan' } });
    expect(Object.keys(latest.vars as object)).toEqual(['plan']);
    expect(screen.getByText('Values to remember')).toBeTruthy();
    expect(screen.getByTestId('flow-hint-member-set-vars').textContent).toContain('until removed');
  });

  it('Update document: Add a field to change adds a row that stays', async () => {
    renderForm(DocUpdateForm, { type: 'doc-update', doctype: '', name: '', values: {} });
    fireEvent.click(await screen.findByTestId('flow-field-test-values-add'));
    expect(screen.getByTestId('flow-field-test-values-row-0')).toBeTruthy();
  });
});
