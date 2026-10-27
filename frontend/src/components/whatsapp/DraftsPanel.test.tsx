// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/whatsappApi', async (orig) => ({
  ...(await orig<typeof import('@/services/whatsappApi')>()),
  approveTemplateDraft: vi.fn(),
  rejectTemplateDraft: vi.fn(),
  getTemplate: vi.fn(),
}));
import { approveTemplateDraft, getTemplate, rejectTemplateDraft, type TemplateDraft } from '@/services/whatsappApi';
import { DraftsPanel } from './DraftsPanel';

const draft: TemplateDraft = {
  name: 'draft-1',
  template_name: 'promo_hello',
  language_code: 'en_US',
  category: 'MARKETING',
  status: 'Pending Review',
  requested_by: 'sam@example.com',
  payload: {
    template_name: 'promo_hello',
    category: 'MARKETING',
    language_code: 'en_US',
    template: 'Hello {{1}}, 20% off today',
    parameter_format: 'POSITIONAL',
    sample_values: 'Ana',
    buttons: [{ type: 'QUICK_REPLY', text: 'Thanks' }],
  },
};

function setup(isAdmin = true) {
  const onChanged = vi.fn();
  render(<DraftsPanel drafts={[draft]} isAdmin={isAdmin} onChanged={onChanged} onUnavailable={vi.fn()} />);
  return onChanged;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getTemplate).mockResolvedValue({ success: true, status: 'PENDING' } as never);
});

describe('DraftsPanel review', () => {
  it('opens the review summary from the draft payload', async () => {
    setup();
    await userEvent.click(screen.getByRole('button', { name: 'Review' }));
    expect(screen.getByRole('heading', { name: 'Check and send' })).toBeInTheDocument();
    expect(screen.getByText('promo_hello', { selector: 'span.font-mono' })).toBeInTheDocument();
    expect(screen.getAllByText('Thanks', { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getByText('Ready to send')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Back to drafts/ }));
    expect(screen.getByRole('button', { name: 'Review' })).toBeInTheDocument();
  });

  it('Approve & submit calls the API once and returns to the list', async () => {
    vi.mocked(approveTemplateDraft).mockResolvedValue({ success: true, submitted_template: 'tpl-9' } as never);
    const onChanged = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Review' }));
    await userEvent.click(screen.getByRole('button', { name: 'Approve & submit' }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(approveTemplateDraft).toHaveBeenCalledTimes(1);
    expect(approveTemplateDraft).toHaveBeenCalledWith('draft-1');
    expect(await screen.findByRole('button', { name: 'Review' })).toBeInTheDocument();
  });

  it('stays in the review when approval fails', async () => {
    vi.mocked(approveTemplateDraft).mockResolvedValue({ success: false, error: 'x', submit_error: 'Meta said no' } as never);
    setup();
    await userEvent.click(screen.getByRole('button', { name: 'Review' }));
    await userEvent.click(screen.getByRole('button', { name: 'Approve & submit' }));
    await waitFor(() => expect(approveTemplateDraft).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('heading', { name: 'Check and send' })).toBeInTheDocument();
  });

  it('Reject asks for a note and calls the API once', async () => {
    vi.mocked(rejectTemplateDraft).mockResolvedValue({ success: true } as never);
    const onChanged = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Review' }));
    await userEvent.click(screen.getByRole('button', { name: 'Reject' }));
    await userEvent.type(screen.getByLabelText(/Note/), 'Too salesy');
    await userEvent.click(screen.getByRole('button', { name: 'Reject draft' }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(rejectTemplateDraft).toHaveBeenCalledTimes(1);
    expect(rejectTemplateDraft).toHaveBeenCalledWith('draft-1', 'Too salesy');
  });

  it('non-admins can view but not decide', async () => {
    setup(false);
    await userEvent.click(screen.getByRole('button', { name: 'View' }));
    expect(screen.queryByRole('button', { name: 'Approve & submit' })).toBeNull();
    expect(screen.getAllByText(/An admin needs to approve/).length).toBeGreaterThan(0);
  });
});
