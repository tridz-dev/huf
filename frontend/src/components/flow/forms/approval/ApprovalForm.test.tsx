// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/contexts/FlowContext', async () => (await import('../__tests__/formTestKit')).contextMock());
vi.mock('@/hooks/flow/useFlowPermissions', async () => (await import('../__tests__/formTestKit')).permissionsMock());
vi.mock('@/services/flow/catalogApi', async () => (await import('../__tests__/formTestKit')).catalogMock());
vi.mock('@/services/flowApi', async (orig) => ({
  ...(await orig<typeof import('@/services/flowApi')>()),
  getApproverRoles: vi.fn().mockResolvedValue([{ name: 'System Manager', group: 'Huf' }, { name: '_Test Role', group: 'Other' }, { name: 'Accountant', group: 'Other' }]),
}));
vi.mock('@/services/flow/formOptionsApi', () => ({
  searchFlowUsers: vi.fn().mockImplementation(async (q: string) =>
    [{ name: 'ada@example.com', full_name: 'Ada Lovelace', label: 'Ada Lovelace (ada@example.com)' }, { name: 'Administrator', full_name: 'Administrator', label: 'Administrator' }]
      .filter((u) => !q || u.name.toLowerCase().includes(q.toLowerCase()) || u.full_name.toLowerCase().includes(q.toLowerCase()))
  ),
  checkFlowUsers: vi.fn().mockImplementation(async (names: string[]) => names.map((n) => ({ name: n, found: n === 'ada@example.com' || n === 'Administrator', full_name: n === 'ada@example.com' ? 'Ada Lovelace' : n }))),
}));

import { ApprovalForm } from './ApprovalForm';
import { latest, renderForm, updateEdges } from '../__tests__/formTestKit';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
afterEach(cleanup);
beforeEach(() => updateEdges.mockClear());

const type = (el: HTMLElement, text: string) => {
  el.textContent = text;
  fireEvent.input(el);
};

describe('ApprovalForm: the message and who decides', () => {
  it('asks what to decide and who can approve, in plain words', async () => {
    renderForm(ApprovalForm, { type: 'human.approval' });
    await screen.findByText('What should the approver decide?');
    expect(screen.getByText('Who can approve')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Literal|\$from|Message for the approver/);
  });

  it('the message keeps its data as {placeholders}', async () => {
    renderForm(ApprovalForm, { type: 'human.approval', message: 'Refund {input.total} to {input.customer.name}?' });
    const box = await screen.findByTestId('flow-field-test-message');
    await waitFor(() => expect(box.querySelectorAll('[data-chip]').length).toBe(2));
    box.appendChild(document.createTextNode(' Please check.'));
    fireEvent.input(box);
    expect(latest.message).toBe('Refund {input.total} to {input.customer.name}? Please check.');
  });

  it('role list hides test roles and explains the others', async () => {
    renderForm(ApprovalForm, { type: 'human.approval', approver_type: 'role' });
    fireEvent.click(await screen.findByTestId('flow-field-test-approver_role'));
    expect(await screen.findByText('Can manage everything')).toBeTruthy();
    expect(screen.queryByText('_Test Role')).toBeNull();
    expect(screen.getByText('Accountant')).toBeTruthy();
  });

  it('people are picked from people who exist; a typo cannot be added', async () => {
    renderForm(ApprovalForm, { type: 'human.approval', approver_type: 'user' });
    const search = await screen.findByTestId('flow-field-test-approver_users-search');
    fireEvent.focus(search);
    fireEvent.change(search, { target: { value: 'Administrtor' } });
    expect(await screen.findByTestId('flow-field-test-approver_users-nobody')).toBeTruthy();
    fireEvent.keyDown(search, { key: 'Enter' });
    expect(latest.approver_users).toBeUndefined();
    fireEvent.change(search, { target: { value: 'ada' } });
    fireEvent.mouseDown(await screen.findByTestId('flow-field-test-approver_users-option-ada@example.com'));
    expect(latest.approver_users).toEqual(['ada@example.com']);
    expect((await screen.findByTestId('flow-field-test-approver_users-chip-ada@example.com')).textContent).toContain('Ada Lovelace');
  });

  it('a saved name nobody has is shown in red and says what to do', async () => {
    renderForm(ApprovalForm, { type: 'human.approval', approver_type: 'user', approver_users: ['Administrtor', 'ada@example.com'] });
    const warning = await screen.findByTestId('flow-field-test-approver_users-unknown');
    expect(warning.textContent).toContain('No one is called "Administrtor"');
    fireEvent.click(screen.getByTestId('flow-field-test-approver_users-remove-Administrtor'));
    expect(latest.approver_users).toEqual(['ada@example.com']);
    await waitFor(() => expect(screen.queryByTestId('flow-field-test-approver_users-unknown')).toBeNull());
  });
});

describe('ApprovalForm: what the approver sees', () => {
  it('has a title, up to six details, and a live card like the one in the bell', async () => {
    renderForm(ApprovalForm, { type: 'human.approval', message: 'Approve this refund?', title: 'Refund for {input.customer.name}' });
    const card = await screen.findByTestId('flow-approval-preview');
    await waitFor(() => expect(within(card).getByTestId('flow-approval-preview-title').textContent).toBe('Refund for Ada Lovelace'));
    expect(within(card).getByTestId('flow-approval-preview-note').textContent).toBe('Approve this refund?');
    expect(within(card).getByText('Approve')).toBeTruthy();
    expect(within(card).getByText('Reject')).toBeTruthy();
  });

  it('with no title the card says what the bell will say', async () => {
    renderForm(ApprovalForm, { type: 'human.approval' });
    expect((await screen.findByTestId('flow-approval-preview-title')).textContent).toBe('Approval needed: Refunds');
  });

  it('details are stored as label and value, show in the card and stop at six', async () => {
    renderForm(ApprovalForm, { type: 'human.approval', message: 'ok', details: [{ label: 'Customer', value: { $from: 'input.customer.name' } }] });
    const card = await screen.findByTestId('flow-approval-preview');
    await waitFor(() => expect(within(card).getByTestId('flow-approval-preview-fact-0').textContent).toBe('CustomerAda Lovelace'));
    fireEvent.click(screen.getByTestId('flow-field-test-details.add'));
    fireEvent.change(screen.getByTestId('flow-field-test-details.1.label'), { target: { value: 'Note' } });
    type(screen.getByTestId('flow-field-test-details.1.value'), 'Rush');
    expect(latest.details).toEqual([{ label: 'Customer', value: { $from: 'input.customer.name' } }, { label: 'Note', value: 'Rush' }]);
    await waitFor(() => expect(within(card).getByTestId('flow-approval-preview-fact-1').textContent).toBe('NoteRush'));
    for (let i = 0; i < 4; i += 1) fireEvent.click(screen.getByTestId('flow-field-test-details.add'));
    expect((latest.details as unknown[]).length).toBe(6);
    expect(screen.queryByTestId('flow-field-test-details.add')).toBeNull();
    fireEvent.click(screen.getByTestId('flow-field-test-details.0.remove'));
    expect((latest.details as unknown[]).length).toBe(5);
  });

  it('removing the last detail leaves no empty list behind', async () => {
    renderForm(ApprovalForm, { type: 'human.approval', details: [{ label: 'A', value: 'b' }] });
    fireEvent.click(await screen.findByTestId('flow-field-test-details.0.remove'));
    expect(latest.details).toBeUndefined();
  });
});

describe('ApprovalForm: the time limit summary', () => {
  it('says what happens if nobody answers and offers to set a limit', async () => {
    renderForm(ApprovalForm, { type: 'human.approval' });
    expect((await screen.findByTestId('flow-approval-timeout-summary-text')).textContent).toBe('The flow waits as long as it takes.');
    expect(screen.getByTestId('flow-approval-timeout-edit').textContent).toBe('Set a time limit');
  });

  it('reads the limit in words and shows the Timed out path only while one is set', async () => {
    renderForm(ApprovalForm, { type: 'human.approval', timeout_ms: 5400000, approve_next: 'end' });
    expect((await screen.findByTestId('flow-approval-timeout-summary-text')).textContent).toBe('After 90 minutes the flow follows the "Timed out" path.');
    expect(screen.getByTestId('flow-branch-timeout')).toBeTruthy();
    expect(screen.getByTestId('flow-approval-timeout-edit').textContent).toBe('Change');
    cleanup();
    renderForm(ApprovalForm, { type: 'human.approval', approve_next: 'end' });
    await screen.findByTestId('flow-approval-timeout-summary');
    expect(screen.queryByTestId('flow-branch-timeout')).toBeNull();
    expect(screen.getByTestId('flow-branch-approve')).toBeTruthy();
  });
});
