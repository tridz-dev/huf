// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/services/whatsappApi', async (orig) => ({ ...(await orig<typeof import('@/services/whatsappApi')>()), getTemplate: vi.fn() }));
import { getTemplate } from '@/services/whatsappApi';
import { TemplateDetailPane } from './TemplateDetailPane';

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
  parameter_format: 'NAMED',
  ttl_seconds: 3600,
  header_format: 'VIDEO',
  named_samples: [{ name: 'first_name', example: 'Ana' }],
  components: {
    header: { type: 'VIDEO', text: '', sample: 'https://x.example/v.mp4' },
    body: { text: 'Hi {{first_name}}, your order shipped', sample_values: [] },
    footer: null,
    buttons: [],
  },
  state: { rejected_reason: '', rejection_recommendation: '', other_info: '', quality_score: 'GREEN', last_event: '', last_event_at: null, last_meta_update: null },
  editable: true,
  edits_left: 4,
  manager_url: '',
  business_id: '',
};

beforeEach(() => vi.mocked(getTemplate).mockResolvedValue(detail as never));

describe('TemplateDetailPane', () => {
  it('shows variable style, validity, header format, named samples and a preview with the sample filled in', async () => {
    render(
      <TemplateDetailPane
        row={{ name: 'tpl-1' } as never} refreshKey={0} onSend={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} onUnavailable={vi.fn()}
      />,
    );
    expect(await screen.findByText('Named, like {{first_name}}')).toBeInTheDocument();
    expect(screen.getByText('Video')).toBeInTheDocument();
    expect(screen.getByText('1 hour')).toBeInTheDocument();
    expect(screen.getByText('{{first_name}}')).toBeInTheDocument();
    expect(screen.getAllByText(/Hi Ana, your order shipped/).length).toBeGreaterThan(0);
    expect(screen.getByText(/4 edits left/)).toBeInTheDocument();
  });

  const pane = () => (
    <TemplateDetailPane
      row={{ name: 'tpl-1' } as never} refreshKey={0} onSend={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} onUnavailable={vi.fn()}
    />
  );

  it("says when Meta changed the template's category", async () => {
    vi.mocked(getTemplate).mockResolvedValue({ ...detail, category: 'MARKETING', previous_category: 'UTILITY', category_changed_by_meta: true } as never);
    render(pane());
    expect(await screen.findByText(/Meta changed this template's category from utility to marketing/i)).toBeInTheDocument();
  });

  it('shows no category notice when nothing was reclassified', async () => {
    render(pane());
    await screen.findByText('Named, like {{first_name}}');
    expect(screen.queryByText(/Meta changed this template/)).toBeNull();
  });

  it('explains an edit block from a refused edit', async () => {
    vi.mocked(getTemplate).mockResolvedValue({
      ...detail, editable: false, editable_reason: 'edit_blocked', editable_message: "Meta won't let this template be edited right now.",
      edit_blocked_until: '2030-01-01T10:00:00+00:00',
    } as never);
    render(pane());
    expect(await screen.findByText(/won't let this template be edited right now/)).toBeInTheDocument();
    expect(screen.getByText(/Try again after/)).toBeInTheDocument();
  });
});

describe('TemplateDetailPane shared templates', () => {
  const sharedRow = {
    name: 'tpl-1',
    shared: true,
    used_by: [{ solution: 'S1', title: 'Orders' }, { solution: 'S2', title: 'Customer care' }],
  } as never;
  const setup = () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onCopy = vi.fn();
    render(<TemplateDetailPane row={sharedRow} refreshKey={0} onSend={vi.fn()} onEdit={onEdit} onDelete={onDelete} onCopy={onCopy} onUnavailable={vi.fn()} />);
    return { onEdit, onDelete, onCopy };
  };

  it('shows the Used by block and Shared pill', async () => {
    setup();
    expect(await screen.findByText('Shared')).toBeInTheDocument();
    expect(screen.getByText('Orders')).toBeInTheDocument();
    expect(screen.getByText(/Meta keeps one copy/)).toBeInTheDocument();
  });

  it('Edit opens the shared dialog; Edit for everyone continues', async () => {
    const { onEdit } = setup();
    await userEvent.click(await screen.findByRole('button', { name: /Edit and resubmit/ }));
    expect(onEdit).not.toHaveBeenCalled();
    expect(screen.getByText('This template is shared')).toBeInTheDocument();
    expect(screen.getByText(/Used by Orders and Customer care\. Editing resubmits it to Meta for all of them/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Edit for everyone' }));
    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onEdit).toHaveBeenCalledWith(expect.anything(), true);
  });

  it('Make a copy suggests name_v2 and Cancel does nothing', async () => {
    const { onEdit, onCopy } = setup();
    await userEvent.click(await screen.findByRole('button', { name: /Edit and resubmit/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Make a copy' }));
    expect(onCopy).toHaveBeenCalledWith(expect.anything(), 'order_update_v2');
    await userEvent.click(screen.getByRole('button', { name: /Edit and resubmit/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onEdit).not.toHaveBeenCalled();
  });

  it('Delete on a shared template asks first and then deletes acknowledged', async () => {
    const { onDelete } = setup();
    await userEvent.click(await screen.findByRole('button', { name: /Delete/ }));
    expect(onDelete).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Delete for everyone' }));
    expect(onDelete).toHaveBeenCalledWith(sharedRow, true);
  });
});
