// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('./TemplatePreview', () => ({ TemplatePreview: () => <div data-testid="preview" /> }));
vi.mock('@/services/whatsappApi', async (orig) => ({
  ...(await orig<typeof import('@/services/whatsappApi')>()),
  sendTemplateMessage: vi.fn(),
  getTemplate: vi.fn(),
}));
import { toast } from 'sonner';
import { getTemplate, sendTemplateMessage, type WhatsAppTemplate } from '@/services/whatsappApi';
import { SendTemplateDialog } from './SendTemplateDialog';

const template = (over: Partial<WhatsAppTemplate> = {}): WhatsAppTemplate => ({
  name: 'order-en', template_name: 'order', language_code: 'en', status: 'APPROVED', template: 'Hi {{1}}, order {{2}} shipped', ...over,
});

const send = vi.mocked(sendTemplateMessage);

function open(t: WhatsAppTemplate | null, props: { gateway?: string; initialTo?: string } = { gateway: 'GW-1' }) {
  const onClose = vi.fn();
  render(<SendTemplateDialog template={t} onClose={onClose} {...props} />);
  return { onClose, user: userEvent.setup() };
}

beforeEach(() => {
  vi.clearAllMocks();
  send.mockResolvedValue({ success: true });
  vi.mocked(getTemplate).mockResolvedValue({ success: false } as never);
});

describe('SendTemplateDialog', () => {
  it('renders nothing while no template is chosen', () => {
    open(null);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows one field per body placeholder and prefills the recipient', () => {
    open(template(), { gateway: 'GW-1', initialTo: '+15550001111' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Recipient')).toHaveValue('+15550001111');
    expect(screen.getByLabelText('{{1}}')).toBeInTheDocument();
    expect(screen.getByLabelText('{{2}}')).toBeInTheDocument();
    expect(screen.getByTestId('preview')).toBeInTheDocument();
  });

  it('keeps Send disabled without a recipient', () => {
    open(template());
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('sends the template by its Meta name with the filled values, then closes', async () => {
    const { onClose, user } = open(template());
    await user.type(screen.getByLabelText('Recipient'), '+15551234567');
    await user.type(screen.getByLabelText('{{1}}'), 'Ann');
    await user.type(screen.getByLabelText('{{2}}'), '42');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(send).toHaveBeenCalledWith({
      gateway_name: 'GW-1', to: '+15551234567', template_name: 'order', body_params: ['Ann', '42'], header_params: [], button_params: [],
    });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith('Template sent');
  });

  it('sends empty strings for untouched placeholders', async () => {
    const { user } = open(template(), { gateway: 'GW-1', initialTo: '+15551234567' });
    await user.type(screen.getByLabelText('{{2}}'), '42');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ body_params: ['', '42'] }));
  });

  it('collects a text header value and sends it as the header', async () => {
    const { user } = open(template({ header_type: 'TEXT', header: 'Order {{1}}', template: 'Body' }), { gateway: 'GW-1', initialTo: '+15551234567' });
    await user.type(screen.getByLabelText('Header value'), 'A-1');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ header_params: ['A-1'], body_params: [] }));
  });

  it('collects an image header link as a media parameter', async () => {
    const { user } = open(template({ header_type: 'IMAGE', template: 'Body' }), { gateway: 'GW-1', initialTo: '+15551234567' });
    await user.type(screen.getByLabelText('Header image link'), ' https://example.com/a.png ');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ header_params: [{ type: 'image', link: 'https://example.com/a.png' }] }));
  });

  it('sends no header when a media header link is left empty', async () => {
    const { user } = open(template({ header_type: 'DOCUMENT', template: 'Body' }), { gateway: 'GW-1', initialTo: '+15551234567' });
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ header_params: [] }));
  });

  it('asks for the end of a dynamic link button and sends it by index', async () => {
    const { user } = open(
      template({
        template: 'Body',
        buttons: [
          { button_type: 'Quick Reply', button_label: 'Hi' },
          { button_type: 'Visit Website', button_label: 'Track', url_type: 'Dynamic', website_url: 'https://x.test/{{1}}' },
        ],
      }),
      { gateway: 'GW-1', initialTo: '+15551234567' },
    );
    expect(screen.queryByLabelText('Hi (end of link)')).toBeNull();
    await user.type(screen.getByLabelText('Track (end of link)'), 'abc123');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ button_params: [{ index: 1, sub_type: 'url', text: 'abc123' }] }));
  });

  it('shows the server error and stays open', async () => {
    send.mockResolvedValue({ success: false, error: 'template_not_found' });
    const { onClose, user } = open(template(), { gateway: 'GW-1', initialTo: '+15551234567' });
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This template does not belong to the selected gateway.');
    expect(onClose).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('does nothing without a gateway', async () => {
    const { user } = open(template(), { initialTo: '+15551234567' });
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(send).not.toHaveBeenCalled();
  });

  it('Cancel closes without sending', async () => {
    const { onClose, user } = open(template());
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalled();
    expect(send).not.toHaveBeenCalled();
  });

  it('sends per-card header media, body and button values for a carousel template', async () => {
    vi.mocked(getTemplate).mockResolvedValue({
      success: true,
      components: { carousel: [0, 1].map(() => ({ header_type: 'IMAGE', body_vars: ['1'], buttons: [{ type: 'QUICK_REPLY', dynamic: false }, { type: 'URL', dynamic: true }] })) },
    } as never);
    const { user } = open(template({ template: 'Hi' }));
    await user.type(screen.getByLabelText('Recipient'), '+15551234567');
    await screen.findAllByText('Image link');
    const field = (id: string) => document.getElementById(id) as HTMLInputElement;
    for (const i of [0, 1]) {
      await user.type(field(`wa-card-${i}-h`), `https://cdn.example/${i}.png`);
      await user.type(field(`wa-card-${i}-b0`), `deal${i}`);
      await user.type(field(`wa-card-${i}-u0`), `pay${i}`);
      await user.type(field(`wa-card-${i}-u1`), `s${i}`);
    }
    await user.click(screen.getByRole('button', { name: 'Send' }));
    const arg = send.mock.calls[0][0];
    expect(arg.carousel_params).toHaveLength(2);
    expect(arg.carousel_params?.[1]).toEqual({
      header: { type: 'image', link: 'https://cdn.example/1.png' },
      body: ['deal1'],
      buttons: [{ index: 0, sub_type: 'quick_reply', text: 'pay1' }, { index: 1, sub_type: 'url', text: 's1' }],
    });
  });
});
