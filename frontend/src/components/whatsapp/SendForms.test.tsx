// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('./TemplateSend', () => ({ TemplateSend: ({ to }: { to: string }) => <div>template picker for {to}</div> }));
vi.mock('@/services/whatsappApi', async (orig) => ({
  ...(await orig<typeof import('@/services/whatsappApi')>()),
  sendTextMessage: vi.fn(),
  sendLocationMessage: vi.fn(),
  sendContactsMessage: vi.fn(),
  sendReactionMessage: vi.fn(),
  sendInteractiveMessage: vi.fn(),
  sendMediaMessage: vi.fn(),
  sendVoiceNote: vi.fn(),
  sendStickerMessage: vi.fn(),
  uploadPublicFile: vi.fn(),
}));
import * as api from '@/services/whatsappApi';
import { SEND_TYPES, SendForm, SendTypePicker, type SendType } from './SendForms';

const OK = { success: true };

function setup(type: SendType, to = '+15551234567') {
  const run = vi.fn(async (send: () => Promise<unknown>, _done: string, reset: () => void) => {
    await send();
    reset();
  });
  const setError = vi.fn();
  const view = render(<SendForm type={type} gateway="GW-1" to={to} run={run as never} sending={false} setError={setError} />);
  return { run, setError, user: userEvent.setup(), ...view };
}

beforeEach(() => {
  vi.clearAllMocks();
  for (const fn of [api.sendTextMessage, api.sendLocationMessage, api.sendContactsMessage, api.sendReactionMessage, api.sendInteractiveMessage, api.sendMediaMessage, api.sendStickerMessage]) {
    (fn as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(OK);
  }
});

describe('send type catalogue', () => {
  it('has a note for every type and no duplicates', () => {
    const values = SEND_TYPES.map((t) => t.value);
    expect(new Set(values).size).toBe(values.length);
    expect(SEND_TYPES.every((t) => t.label && t.note)).toBe(true);
    expect(values).toEqual(expect.arrayContaining(['text', 'template', 'image', 'location', 'contact', 'reaction', 'buttons', 'list', 'cta_url']));
  });

  it('picker shows the current type', () => {
    render(<SendTypePicker value="location" onChange={() => {}} />);
    expect(screen.getByRole('combobox', { name: 'Message type' })).toHaveTextContent('Location');
  });
});

describe('text form', () => {
  it('disables Send until there is text and a recipient', async () => {
    const { user } = setup('text', '');
    const send = screen.getByRole('button', { name: 'Send' });
    expect(send).toBeDisabled();
    await user.type(screen.getByLabelText('Message text'), 'hi');
    expect(send).toBeDisabled(); // still no recipient
  });

  it('sends through the shared runner and clears the box', async () => {
    const { run, user } = setup('text');
    await user.type(screen.getByLabelText('Message text'), 'hello there');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(run).toHaveBeenCalledWith(expect.any(Function), 'Message sent', expect.any(Function));
    expect(api.sendTextMessage).toHaveBeenCalledWith('GW-1', '+15551234567', 'hello there');
    expect(screen.getByLabelText('Message text')).toHaveValue('');
  });
});

describe('template form', () => {
  it('delegates to the template picker for the recipient', () => {
    setup('template');
    expect(screen.getByText('template picker for +15551234567')).toBeInTheDocument();
  });
});

describe('location form', () => {
  it('rejects a missing or out-of-range position without sending', async () => {
    const { user } = setup('location');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findAllByText('Enter a latitude and longitude')).toHaveLength(2);
    await user.type(screen.getByLabelText('Latitude'), '91');
    await user.type(screen.getByLabelText('Longitude'), '10');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText(/Latitude is between/)).toBeInTheDocument();
    expect(api.sendLocationMessage).not.toHaveBeenCalled();
  });

  it('sends numeric coordinates and resets', async () => {
    const { user } = setup('location');
    await user.type(screen.getByLabelText('Latitude'), '12.5');
    await user.type(screen.getByLabelText('Longitude'), '-77.25');
    await user.type(screen.getByLabelText('Place name'), 'Office');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendLocationMessage).toHaveBeenCalledWith('GW-1', '+15551234567', { latitude: 12.5, longitude: -77.25, name: 'Office', address: '' });
    expect(screen.getByLabelText('Latitude')).toHaveValue('');
  });
});

describe('contact form', () => {
  it('needs a name and a phone or email', async () => {
    const { user } = setup('contact');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Add the contact name')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Contact name'), 'Ann');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Add a phone number or an email')).toBeInTheDocument();
    expect(api.sendContactsMessage).not.toHaveBeenCalled();
  });

  it('builds the card with only the fields given', async () => {
    const { user } = setup('contact');
    await user.type(screen.getByLabelText('Contact name'), '  Ann Lee ');
    await user.type(screen.getByLabelText('Contact phone'), '+15550001111');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendContactsMessage).toHaveBeenCalledWith('GW-1', '+15551234567', [
      { name: { formatted_name: 'Ann Lee' }, phones: [{ phone: '+15550001111' }], emails: undefined, org: undefined },
    ]);
  });
});

describe('reaction form', () => {
  it('needs a message id and, to add, an emoji', async () => {
    const { user } = setup('reaction');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Add the ID of the message to react to')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Message ID'), 'wamid.X');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Add an emoji')).toBeInTheDocument();
    expect(api.sendReactionMessage).not.toHaveBeenCalled();
  });

  it('sends and removes a reaction', async () => {
    const { run, user } = setup('reaction');
    await user.type(screen.getByLabelText('Message ID'), 'wamid.X');
    await user.type(screen.getByLabelText('Emoji'), '👍');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendReactionMessage).toHaveBeenLastCalledWith('GW-1', '+15551234567', 'wamid.X', '👍', false);
    expect(run).toHaveBeenLastCalledWith(expect.any(Function), 'Reaction sent', expect.any(Function));
    await user.click(screen.getByRole('button', { name: 'Remove reaction' }));
    expect(api.sendReactionMessage).toHaveBeenLastCalledWith('GW-1', '+15551234567', 'wamid.X', expect.any(String), true);
    expect(run).toHaveBeenLastCalledWith(expect.any(Function), 'Reaction removed', expect.any(Function));
  });
});

describe('interactive forms', () => {
  it('reply buttons: validates then sends the buttons', async () => {
    const { user } = setup('buttons');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Add the message text')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Interactive message text'), 'Pick one');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Every button needs a label')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Button 1 label'), 'Yes');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendInteractiveMessage).toHaveBeenCalledWith(
      'GW-1', '+15551234567',
      expect.objectContaining({ kind: 'buttons', body: 'Pick one', buttons: [{ id: 'btn_1', title: 'Yes' }] }),
    );
  });

  it('reply buttons: caps at three and can remove one', async () => {
    const { user } = setup('buttons');
    const add = () => screen.getByRole('button', { name: /Add button/ });
    await user.click(add());
    await user.click(add());
    expect(screen.getByLabelText('Button 3 label')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add button/ })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Remove button 2' }));
    expect(screen.queryByLabelText('Button 3 label')).toBeNull();
    expect(screen.getByRole('button', { name: /Add button/ })).toBeInTheDocument();
  });

  it('list: needs a menu label and items, sends sections', async () => {
    const { user } = setup('list');
    await user.type(screen.getByLabelText('Interactive message text'), 'Menu');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Add the label for the list button')).toBeInTheDocument();
    await user.type(screen.getByLabelText('List button label'), 'Choose');
    await user.type(screen.getByLabelText('Item 1 title'), 'Soup');
    await user.type(screen.getByLabelText('Item 1 description'), 'Hot');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendInteractiveMessage).toHaveBeenCalledWith(
      'GW-1', '+15551234567',
      expect.objectContaining({
        kind: 'list', buttonText: 'Choose',
        sections: [{ title: 'Options', rows: [{ id: 'row_1', title: 'Soup', description: 'Hot' }] }],
      }),
    );
  });

  it('link button: requires an https link', async () => {
    const { user } = setup('cta_url');
    await user.type(screen.getByLabelText('Interactive message text'), 'Visit us');
    await user.type(screen.getByLabelText('Link button label'), 'Open');
    await user.type(screen.getByLabelText('Link address'), 'http://insecure.example');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('The link must start with https://')).toBeInTheDocument();
    expect(api.sendInteractiveMessage).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText('Link address'));
    await user.type(screen.getByLabelText('Link address'), 'https://example.com/x');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendInteractiveMessage).toHaveBeenCalledWith('GW-1', '+15551234567', expect.objectContaining({ kind: 'cta_url', url: 'https://example.com/x', displayText: 'Open' }));
  });
});

describe('send payloads (unchanged)', () => {
  it('voice note: sends via sendVoiceNote, rejects non-ogg', async () => {
    vi.mocked(api.sendVoiceNote).mockResolvedValue({ success: true });
    const { user } = setup('audio');
    await user.click(screen.getByLabelText('Send as voice note'));
    await user.type(screen.getByLabelText('Media link'), 'https://example.com/a.mp3');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText(/must be an Ogg file/)).toBeInTheDocument();
    expect(api.sendVoiceNote).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText('Media link'));
    await user.type(screen.getByLabelText('Media link'), 'https://example.com/a.ogg');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendVoiceNote).toHaveBeenCalledWith('GW-1', '+15551234567', { link: 'https://example.com/a.ogg', fileUrl: undefined });
  });

  it('document: passes the uploaded file name as filename', async () => {
    vi.mocked(api.uploadPublicFile).mockResolvedValue({ fileUrl: '/files/r.pdf' });
    const { user } = setup('document');
    await user.upload(screen.getByLabelText('Media file'), new File(['x'], 'r.pdf', { type: 'application/pdf' }));
    await screen.findByText('r.pdf');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendMediaMessage).toHaveBeenCalledWith('GW-1', '+15551234567', { kind: 'document', link: '', fileUrl: '/files/r.pdf', caption: '', filename: 'r.pdf' });
  });

  it('media: a non-https link shows a field error and does not send', async () => {
    const { user } = setup('image');
    await user.type(screen.getByLabelText('Media link'), 'http://example.com/a.png');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('The link must start with https://')).toBeInTheDocument();
    expect(screen.getByLabelText('Media link')).toHaveAttribute('aria-invalid', 'true');
    expect(api.sendMediaMessage).not.toHaveBeenCalled();
  });

  it('list: sends the full previous payload shape', async () => {
    const { user } = setup('list');
    await user.type(screen.getByLabelText('Header'), 'H');
    await user.type(screen.getByLabelText('Interactive message text'), 'Menu');
    await user.type(screen.getByLabelText('Footer'), 'F');
    await user.type(screen.getByLabelText('List button label'), 'Choose');
    await user.type(screen.getByLabelText('Item 1 title'), 'Soup');
    await user.click(screen.getByRole('button', { name: /Add item/ }));
    await user.type(screen.getByLabelText('Item 2 title'), 'Tea');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendInteractiveMessage).toHaveBeenCalledWith('GW-1', '+15551234567', {
      kind: 'list', body: 'Menu', header: 'H', footer: 'F', buttonText: 'Choose', displayText: '', url: '',
      buttons: [{ id: 'btn_1', title: '' }],
      sections: [{ title: 'Options', rows: [{ id: 'row_1', title: 'Soup', description: undefined }, { id: 'row_2', title: 'Tea', description: undefined }] }],
    });
  });

  it('reaction: keeps the message id after sending, clears the emoji', async () => {
    const { user } = setup('reaction');
    await user.type(screen.getByLabelText('Message ID'), 'wamid.X');
    await user.type(screen.getByLabelText('Emoji'), '👍');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(screen.getByLabelText('Message ID')).toHaveValue('wamid.X');
    expect(screen.getByLabelText('Emoji')).toHaveValue('');
  });

  it('errors clear once the form is fixed and resubmitted', async () => {
    const { user } = setup('contact');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Add the contact name')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Contact name'), 'Ann');
    await user.type(screen.getByLabelText('Contact email'), 'a@b.co');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(screen.queryByText('Add the contact name')).toBeNull();
    expect(api.sendContactsMessage).toHaveBeenCalled();
  });
});

describe('media forms (non-voice)', () => {
  it('image: needs a link or file, then sends the link with the caption', async () => {
    const { user } = setup('image');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Add a file or paste a public link')).toBeInTheDocument();
    expect(api.sendMediaMessage).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText('Media link'), 'https://example.com/a.png');
    await user.type(screen.getByLabelText('Media caption'), 'Look');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendMediaMessage).toHaveBeenCalledWith('GW-1', '+15551234567', expect.objectContaining({ kind: 'image', link: 'https://example.com/a.png', caption: 'Look' }));
  });

  it('sticker: asks for a file or link', async () => {
    const { user } = setup('sticker');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Add a file or paste a public link')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Media link'), 'https://example.com/s.webp');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendStickerMessage).toHaveBeenCalledWith('GW-1', '+15551234567', { link: 'https://example.com/s.webp', fileUrl: undefined });
  });

  it('upload failure is surfaced and nothing is attached', async () => {
    vi.mocked(api.uploadPublicFile).mockResolvedValue({ success: false, error: 'upload_failed', message: 'Too big' });
    const { setError, user } = setup('image');
    await user.upload(screen.getByLabelText('Media file'), new File(['x'], 'a.png', { type: 'image/png' }));
    expect(setError).toHaveBeenLastCalledWith(expect.objectContaining({ message: 'Too big' }));
    expect(screen.getByText('or upload a file')).toBeInTheDocument();
  });

  it('upload success shows the file name and sends it by path', async () => {
    vi.mocked(api.uploadPublicFile).mockResolvedValue({ fileUrl: '/files/a.png' });
    const { user } = setup('image');
    await user.upload(screen.getByLabelText('Media file'), new File(['x'], 'a.png', { type: 'image/png' }));
    expect(await screen.findByText('a.png')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(api.sendMediaMessage).toHaveBeenCalledWith('GW-1', '+15551234567', expect.objectContaining({ kind: 'image', fileUrl: '/files/a.png' }));
  });
});
