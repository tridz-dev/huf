// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';

// jsdom has no top layer; answering ':modal' directly keeps Radix Select opening fast.
const originalMatches = Element.prototype.matches;
Element.prototype.matches = function (this: Element, selector: string) {
  return selector === ':modal' ? false : originalMatches.call(this, selector);
};

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/contexts/PermissionsContext', () => ({ usePermissions: () => ({ hufRole: 'Huf Admin' }) }));
vi.mock('@/contexts/SocketContext', () => ({ useSocket: () => null }));
vi.mock('@/services/whatsappApi', async (orig) => ({
  ...(await orig<typeof import('@/services/whatsappApi')>()),
  listTemplates: vi.fn(),
  listTemplateDrafts: vi.fn(),
  getTemplate: vi.fn(),
  syncTemplates: vi.fn(),
  deleteTemplate: vi.fn(),
}));
vi.mock('@/services/solutionsApi', () => ({ listSolutions: vi.fn() }));
const wizard = vi.hoisted(() => ({ props: null as null | Record<string, unknown> }));
vi.mock('./TemplateWizard', () => ({
  TemplateWizard: (props: Record<string, unknown>) => {
    wizard.props = props;
    return (
      <div>
        <p>wizard {props.initial ? 'edit' : props.copyFrom ? 'copy' : 'create'}</p>
        <button onClick={() => (props.onSharedConflict as (u: unknown[]) => void)?.([{ solution: 'S1', title: 'Orders' }])}>Trigger shared</button>
        <button onClick={() => (props.onCancel as () => void)()}>Cancel wizard</button>
        <button onClick={() => (props.onDone as (r: unknown) => void)({ kind: 'submitted', name: 'new_one' })}>Finish wizard</button>
      </div>
    );
  },
}));

import { getTemplate, listTemplateDrafts, listTemplates, type TemplateDetail } from '@/services/whatsappApi';
import { listSolutions } from '@/services/solutionsApi';
import { TemplatesTab } from './TemplatesTab';
import { categoryLabel } from './templateModel';

const row = { name: 'tpl-1', template_name: 'order_update', language_code: 'en_US', category: 'UTILITY', status: 'APPROVED', template: 'Hi' };
const detail = {
  success: true,
  name: 'tpl-1',
  template_id: '1',
  template_name: 'order_update',
  language_code: 'en_US',
  category: 'UTILITY',
  correct_category: 'UTILITY',
  category_change_pending: false,
  status: 'APPROVED',
  components: { header: null, body: { text: 'Order {{1}} shipped', sample_values: ['A1'] }, footer: null, buttons: [] },
  state: { rejected_reason: '', rejection_recommendation: '', other_info: '', quality_score: 'GREEN', last_event: '', last_event_at: null, last_meta_update: null },
  editable: true,
  edits_left: 3,
  manager_url: '',
  business_id: '',
} as unknown as TemplateDetail & { success: true };

function Search() {
  return <output data-testid="search">{useLocation().search}</output>;
}
const open = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <TemplatesTab gateway="GW-1" />
      <Search />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  wizard.props = null;
  vi.mocked(listTemplates).mockResolvedValue({ success: true, templates: [row], manager_url: '', business_id: '' } as never);
  vi.mocked(listTemplateDrafts).mockResolvedValue({ success: true, drafts: [] } as never);
  vi.mocked(getTemplate).mockResolvedValue(detail as never);
  vi.mocked(listSolutions).mockResolvedValue([{ name: 'S1', title: 'Orders' }, { name: 'S2', title: 'Care' }] as never);
});

describe('TemplatesTab wizard wiring', () => {
  it('opens the wizard for a new template, linkable through ?new=1, and Cancel returns to the list', async () => {
    open('/?tab=templates');
    await userEvent.click(await screen.findByRole('button', { name: /New template/ }));
    expect(screen.getByText('wizard create')).toBeInTheDocument();
    expect(screen.getByTestId('search')).toHaveTextContent('new=1');
    expect(wizard.props).toMatchObject({ gatewayName: 'GW-1', isAdmin: true });
    await userEvent.click(screen.getByRole('button', { name: 'Cancel wizard' }));
    expect(await screen.findByRole('button', { name: /New template/ })).toBeInTheDocument();
    expect(screen.getByTestId('search')).not.toHaveTextContent('new=1');
    expect(screen.getByTestId('search')).toHaveTextContent('tab=templates');
  });

  it('?new=1 opens the wizard straight away', async () => {
    open('/?tab=templates&new=1');
    expect(await screen.findByText('wizard create')).toBeInTheDocument();
  });

  it('?edit=<name> loads the template and prefills the wizard with edits left', async () => {
    open('/?tab=templates&edit=tpl-1');
    expect(await screen.findByText('wizard edit')).toBeInTheDocument();
    expect(getTemplate).toHaveBeenCalledWith('tpl-1');
    expect(wizard.props).toMatchObject({ docName: 'tpl-1', editsLeft: 3 });
    expect(wizard.props?.initial).toMatchObject({ name: 'order_update', body: 'Order {{1}} shipped', samples: { 1: 'A1' } });
  });

  it('Edit from the detail pane sets ?edit= and refreshes the list when the wizard finishes', async () => {
    open('/?tab=templates');
    await userEvent.click(await screen.findByRole('button', { name: /Edit and resubmit/ }));
    await screen.findByText('wizard edit');
    expect(screen.getByTestId('search')).toHaveTextContent('edit=tpl-1');
    const loads = vi.mocked(listTemplates).mock.calls.length;
    await userEvent.click(screen.getByRole('button', { name: 'Finish wizard' }));
    await waitFor(() => expect(vi.mocked(listTemplates).mock.calls.length).toBeGreaterThan(loads));
    expect(screen.getByTestId('search')).not.toHaveTextContent('edit=');
  });
});

describe('TemplatesTab list', () => {
  it('title-cases any category in the list', async () => {
    vi.mocked(listTemplates).mockResolvedValue({
      success: true, templates: [{ ...row, category: 'AUTHENTICATION' }], manager_url: '', business_id: '',
    } as never);
    render(<MemoryRouter><TemplatesTab gateway="GW-1" /></MemoryRouter>);
    expect(await screen.findByText(/Authentication · English \(US\)/)).toBeInTheDocument();
    expect(categoryLabel('MARKETING')).toBe('Marketing');
    expect(categoryLabel(null)).toBe('');
  });
});

describe('TemplatesTab solutions', () => {
  const rows = [
    { ...row, name: 'a', template_name: 'order_update', used_by: [{ solution: 'S1', title: 'Orders' }, { solution: 'S2', title: 'Care' }], shared: true },
    { ...row, name: 'b', template_name: 'care_hello', used_by: [{ solution: 'S2', title: 'Care' }], shared: false },
  ];
  beforeEach(() => {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
  Element.prototype.scrollIntoView = () => {};
    vi.mocked(listTemplates).mockResolvedValue({ success: true, templates: rows, manager_url: '', business_id: '' } as never);
  });

  it('shows Used by chips and a Shared pill per row', async () => {
    open('/?tab=templates');
    await screen.findByText('care_hello');
    expect(screen.getAllByTestId('used-by').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Shared').length).toBeGreaterThan(0);
  });

  it('the Any solution filter narrows the list', async () => {
    open('/?tab=templates');
    await screen.findByText('care_hello');
    await userEvent.click(await screen.findByLabelText('Filter by solution'));
    await userEvent.click(await screen.findByText('Orders', { selector: '[role="option"] *, [role="option"]' }));
    expect(screen.queryByText('care_hello')).toBeNull();
    expect(screen.getAllByText('order_update').length).toBeGreaterThan(0);
  });

  it('scopeSolution passes the solution to the API and hides account-level actions and the filter', async () => {
    render(<MemoryRouter><TemplatesTab gateway="GW-1" scopeSolution="S1" /></MemoryRouter>);
    await screen.findByText('care_hello');
    expect(vi.mocked(listTemplates)).toHaveBeenCalledWith('GW-1', undefined, 'S1');
    expect(screen.queryByRole('button', { name: /Sync/ })).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'Filter by solution' })).toBeNull();
    expect(screen.queryByRole('tab', { name: /Drafts/ })).toBeNull();
    expect(listSolutions).not.toHaveBeenCalled();
  });
});

describe('TemplatesTab wizard follow-ups', () => {
  it('reopens the shared dialog on a conflict; Edit for everyone acknowledges the retry', async () => {
    open('/?tab=templates&edit=tpl-1');
    await screen.findByText('wizard edit');
    expect(wizard.props?.acknowledgeShared).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: 'Trigger shared' }));
    expect(await screen.findByText('This template is shared')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Edit for everyone' }));
    await waitFor(() => expect(wizard.props?.acknowledgeShared).toBe(true));
    expect(screen.getByText('wizard edit')).toBeInTheDocument();
  });

  it('Make a copy from the conflict dialog opens create mode with the source as copyFrom', async () => {
    open('/?tab=templates&edit=tpl-1');
    await screen.findByText('wizard edit');
    await userEvent.click(screen.getByRole('button', { name: 'Trigger shared' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Make a copy' }));
    await screen.findByText('wizard copy');
    expect((wizard.props?.copyFrom as { name: string }).name).toBe('order_update');
  });
});
