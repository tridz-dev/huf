// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/whatsappApi', async (orig) => {
  const actual = await orig<typeof import('@/services/whatsappApi')>();
  return {
    ...actual,
    createTemplate: vi.fn(),
    createTemplateDraft: vi.fn(),
    editTemplate: vi.fn(),
    uploadPublicFile: vi.fn(),
  };
});

import { SharedTemplateError, createTemplate, createTemplateDraft, editTemplate, errorText } from '@/services/whatsappApi';
import { emptyDraft, type TemplateWizardDraft } from '../template/draft';
import { addButton, buttonBlocker, switchVariableType } from './draftActions';
import { TemplateWizard } from './index';

const create = vi.mocked(createTemplate);
const draftApi = vi.mocked(createTemplateDraft);
const edit = vi.mocked(editTemplate);

const onDone = vi.fn();
const onCancel = vi.fn();

function setup(props: Partial<React.ComponentProps<typeof TemplateWizard>> = {}) {
  return render(<TemplateWizard gatewayName="gw" isAdmin onDone={onDone} onCancel={onCancel} {...(props as object)} />);
}

const type = (label: string | RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const next = () => fireEvent.click(screen.getByRole('button', { name: 'Next' }));

function pickMarketing() {
  fireEvent.click(screen.getByRole('radio', { name: /Default/ }));
  next();
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('step 1', () => {
  it('gates Next on a selectable type and disables unavailable ones', () => {
    setup();
    const nextBtn = screen.getByRole('button', { name: 'Next' });
    expect(screen.getByRole('radio', { name: /Default/ })).toBeChecked();
    expect(nextBtn).toBeEnabled();
    expect(screen.getByRole('tab', { name: 'Authentication' })).toBeDisabled();
    expect(screen.queryByText(/Authentication:/, { selector: 'p' })).toBeNull();
    expect(screen.getAllByText('Coming soon').length).toBeGreaterThan(0);
    expect(screen.getByRole('radio', { name: /Catalogue/ })).toBeDisabled();
    expect(screen.getByRole('link', { name: /template library/ })).toHaveAttribute('rel', 'noopener noreferrer');
    next();
    expect(screen.getByRole('region', { name: 'Write it' })).toBeInTheDocument();
  });
});

describe('step 2', () => {
  beforeEach(() => {
    setup();
    pickMarketing();
  });

  it('inserts a variable at the caret and asks for a sample', () => {
    const body = screen.getByLabelText('Body') as HTMLTextAreaElement;
    fireEvent.change(body, { target: { value: 'Hi , welcome' } });
    body.setSelectionRange(3, 3);
    fireEvent.click(screen.getByRole('toolbar', { name: 'Formatting' }).querySelector('button:last-child') as HTMLElement);
    expect(body.value).toBe('Hi {{1}}, welcome');
    const sample = screen.getByLabelText(/Body \{\{1\}\}/);
    fireEvent.blur(sample);
    expect(screen.getByText('Add a sample')).toBeInTheDocument();
    fireEvent.change(sample, { target: { value: 'Alex' } });
    expect(screen.queryByText('Add a sample')).toBeNull();
  });

  it('formats the selection from the toolbar', () => {
    const body = screen.getByLabelText('Body') as HTMLTextAreaElement;
    fireEvent.change(body, { target: { value: 'big news' } });
    body.setSelectionRange(0, 3);
    fireEvent.click(screen.getByRole('button', { name: 'Bold' }));
    expect(body.value).toBe('*big* news');
  });

  it('converts variables when the type changes', () => {
    const body = screen.getByLabelText('Body') as HTMLTextAreaElement;
    fireEvent.change(body, { target: { value: 'Hi {{1}}, hello' } });
    fireEvent.change(screen.getByLabelText(/Body \{\{1\}\}/), { target: { value: 'Alex' } });
    fireEvent.click(screen.getByRole('radio', { name: 'Name variables' }));
    expect(body.value).toBe('Hi {{variable_1}}, hello');
    expect((screen.getByLabelText(/Body \{\{variable_1\}\}/) as HTMLInputElement).value).toBe('Alex');
  });

  it('shows the name error after blur and keeps Next blocked until valid', () => {
    const name = screen.getByLabelText('Template name');
    expect(screen.queryByText('Name is required.')).toBeNull();
    fireEvent.blur(name);
    expect(screen.getByText('Name is required.')).toBeInTheDocument();
    expect(name).toHaveAttribute('aria-invalid', 'true');
    next();
    expect(screen.getByRole('region', { name: 'Write it' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toHaveAttribute('aria-disabled', 'true');
  });

  it('suggests a slug for the name', () => {
    type('Template name', 'Order Update');
    fireEvent.click(screen.getByRole('button', { name: 'Use order_update' }));
    expect((screen.getByLabelText('Template name') as HTMLInputElement).value).toBe('order_update');
  });

  it('applies the button rules', () => {
    const add = (label: string) => {
      fireEvent.keyDown(screen.getByRole('button', { name: 'Add button' }), { key: 'Enter' });
      fireEvent.click(screen.getByRole('menuitem', { name: new RegExp(label) }));
    };
    add('Call phone number');
    expect(screen.getByRole('group', { name: /Button 1: Call phone number/ })).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole('button', { name: 'Add button' }), { key: 'Enter' });
    expect(screen.getByRole('menuitem', { name: /Call phone number/ })).toHaveAttribute('aria-disabled', 'true');
  });
});

describe('draft actions', () => {
  it('groups quick replies and enforces per-type limits', () => {
    let d: TemplateWizardDraft = emptyDraft();
    d = addButton(d, 'QUICK_REPLY', 'a');
    d = addButton(d, 'URL', 'b');
    d = addButton(d, 'QUICK_REPLY', 'c');
    expect(d.buttons.map((b) => b.id)).toEqual(['a', 'c', 'b']);
    d = addButton(addButton(d, 'URL', 'd'), 'PHONE_NUMBER', 'e');
    expect(buttonBlocker(d, 'URL')).toMatch(/2 website/);
    expect(buttonBlocker(d, 'PHONE_NUMBER')).toMatch(/one phone/i);
    expect(buttonBlocker(d, 'QUICK_REPLY')).toBeNull();
  });

  it('moves header and body samples when switching variable type', () => {
    const d = {
      ...emptyDraft(),
      header: { type: 'text' as const, text: 'Order {{1}}', mediaSample: '' },
      body: 'Hi {{1}} and {{2}}',
      samples: { '1': 'A', '2': 'B', 'header.1': 'H' },
    };
    const out = switchVariableType(d, 'name');
    expect(out.header.text).toBe('Order {{variable_1}}');
    expect(out.body).toBe('Hi {{variable_1}} and {{variable_2}}');
    expect(out.samples).toEqual({ variable_1: 'A', variable_2: 'B', 'header.variable_1': 'H' });
  });
});

describe('final step', () => {
  async function toReview() {
    pickMarketing();
    type('Template name', 'order_update');
    fireEvent.change(screen.getByLabelText('Body'), { target: { value: 'Your order has shipped' } });
    next();
    expect(screen.getByRole('region', { name: 'Check and send' })).toBeInTheDocument();
  }

  it('lets admins submit to WhatsApp', async () => {
    create.mockResolvedValue({ success: true, name: 'order_update' });
    setup();
    await toReview();
    expect(screen.getByText(/up to 24 hours/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Submit to WhatsApp' }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ kind: 'submitted', name: 'order_update' }));
    expect(create).toHaveBeenCalledWith('gw', expect.objectContaining({ template_name: 'order_update', category: 'MARKETING' }));
    expect(draftApi).not.toHaveBeenCalled();
  });

  it('asks non-admins to request approval', async () => {
    draftApi.mockResolvedValue({ success: true, name: 'd1', status: 'Pending', draft: {} as never });
    setup({ isAdmin: false });
    await toReview();
    expect(screen.queryByRole('button', { name: 'Submit to WhatsApp' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Request approval' }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ kind: 'draft', name: 'd1' }));
    expect(create).not.toHaveBeenCalled();
  });

  it('jumps back to the write step on field errors from the backend', async () => {
    create.mockResolvedValue({
      success: false,
      error: 'validation_failed',
      errors: [{ field: 'template_name', code: 'taken', message: 'That name is already used.' }],
    });
    setup();
    await toReview();
    fireEvent.click(screen.getByRole('button', { name: 'Submit to WhatsApp' }));
    await waitFor(() => expect(screen.getByRole('region', { name: 'Write it' })).toBeInTheDocument());
    expect(within(screen.getByRole('region', { name: 'Write it' })).getAllByText('That name is already used.').length).toBeGreaterThan(0);
    expect(onDone).not.toHaveBeenCalled();
  });

  it('shows generic errors on the review step', async () => {
    create.mockResolvedValue({ success: false, error: 'request_failed', message: 'Network down' });
    setup();
    await toReview();
    fireEvent.click(screen.getByRole('button', { name: 'Submit to WhatsApp' }));
    expect(await screen.findByText('Network down')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Check and send' })).toBeInTheDocument();
  });

  it('maps a top-level invalid_name code onto the name field and the setup step', async () => {
    create.mockResolvedValue({ success: false, error: 'invalid_name', message: 'Name rejected by WhatsApp.' });
    setup();
    await toReview();
    fireEvent.click(screen.getByRole('button', { name: 'Submit to WhatsApp' }));
    await waitFor(() => expect(screen.getByRole('region', { name: 'Write it' })).toBeInTheDocument());
    expect(within(screen.getByRole('region', { name: 'Write it' })).getByText('Name rejected by WhatsApp.')).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
  });

  it('sends a category error to the type step in create mode', async () => {
    create.mockResolvedValue({ success: false, error: 'invalid_category', message: 'Category rejected by WhatsApp.' });
    setup();
    await toReview();
    fireEvent.click(screen.getByRole('button', { name: 'Submit to WhatsApp' }));
    await waitFor(() => expect(screen.getByRole('region', { name: 'Pick a type' })).toBeInTheDocument());
    expect(screen.getByText('Category rejected by WhatsApp.')).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
  });

  it('keeps an unmapped error as the general notice on the review step', async () => {
    create.mockResolvedValue({ success: false, error: 'something_unknown', message: 'Unexpected problem.' });
    setup();
    await toReview();
    fireEvent.click(screen.getByRole('button', { name: 'Submit to WhatsApp' }));
    expect(await screen.findByText(errorText({ success: false, error: 'something_unknown', message: 'Unexpected problem.' }))).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Check and send' })).toBeInTheDocument();
  });
});

describe('edit mode', () => {
  const initial: TemplateWizardDraft = { ...emptyDraft('UTILITY'), name: 'order_update', language: 'en_US', body: 'Your order shipped' };

  it('skips the type step, locks name and language and uses editTemplate', async () => {
    edit.mockResolvedValue({ success: true, name: 'order_update', edits_left: 2 });
    setup({ initial, docName: 'tpl-1', editsLeft: 2 });
    expect(screen.getByRole('region', { name: 'Write it' })).toBeInTheDocument();
    expect(screen.getByLabelText('Template name')).toBeDisabled();
    expect(screen.getByRole('combobox', { name: /Language/ })).toBeDisabled();
    expect(screen.getByText(/Edits left: 2/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Previous' })).toBeNull();
    next();
    fireEvent.click(screen.getByRole('button', { name: 'Submit changes to WhatsApp' }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ kind: 'edited', name: 'order_update' }));
    expect(edit).toHaveBeenCalledWith('tpl-1', expect.objectContaining({ template: 'Your order shipped' }), undefined);
  });

  it('keeps a category error on the write step, since edit mode has no type step', async () => {
    edit.mockResolvedValue({ success: false, error: 'invalid_category', message: 'Category rejected by WhatsApp.' });
    setup({ initial, docName: 'tpl-1', editsLeft: 2 });
    next();
    fireEvent.click(screen.getByRole('button', { name: 'Submit changes to WhatsApp' }));
    await waitFor(() => expect(screen.getByRole('region', { name: 'Write it' })).toBeInTheDocument());
    expect(screen.getByText('Category rejected by WhatsApp.')).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
  });

  it('shows Meta\'s title, message, subcode and trace for a refused edit, and that no edit was used', async () => {
    edit.mockResolvedValue({
      success: false,
      error: 'edit_failed',
      message: "Meta won't let this template be edited right now (it may still be in review, or was just approved/reclassified). Try again later or create a new version. Meta says: The status for this message template can't be changed. You can only delete or add templates.",
      user_title: "Message template status can't be changed",
      user_msg: "The status for this message template can't be changed. You can only delete or add templates.",
      graph_code: 100,
      subcode: 2388039,
      kind: 'edit_blocked',
      trace_id: 'AbC123xyz',
      quota_used: false,
    });
    setup({ initial, docName: 'tpl-1', editsLeft: 2 });
    next();
    fireEvent.click(screen.getByRole('button', { name: 'Submit changes to WhatsApp' }));
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText("Message template status can't be changed")).toBeInTheDocument();
    expect(within(alert).getByText(/You can only delete or add templates/)).toBeInTheDocument();
    expect(within(alert).getByText(/Meta won't let this template be edited right now/)).toBeInTheDocument();
    expect(within(alert).getByText(/subcode 2388039/)).toBeInTheDocument();
    expect(within(alert).getByText(/trace AbC123xyz/)).toBeInTheDocument();
    expect(within(alert).getByText(/did not use up an edit/)).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
  });
});

describe('shared template edit', () => {
  const initial: TemplateWizardDraft = { ...emptyDraft('UTILITY'), name: 'order_update', language: 'en_US', body: 'Your order shipped' };
  const usedBy = [{ solution: 'S1', title: 'Orders' }];
  const submitEdit = () => {
    next();
    fireEvent.click(screen.getByRole('button', { name: 'Submit changes to WhatsApp' }));
  };

  it('catches SharedTemplateError, resets busy and reports it through onSharedConflict', async () => {
    edit.mockRejectedValue(new SharedTemplateError(usedBy));
    const onSharedConflict = vi.fn();
    setup({ initial, docName: 'tpl-1', onSharedConflict });
    submitEdit();
    await waitFor(() => expect(onSharedConflict).toHaveBeenCalledWith(usedBy));
    expect(screen.getByRole('button', { name: 'Submit changes to WhatsApp' })).toBeEnabled();
    expect(onDone).not.toHaveBeenCalled();
  });

  it('sends acknowledge_shared only when acknowledged', async () => {
    edit.mockResolvedValue({ success: true, name: 'order_update', edits_left: 2 });
    setup({ initial, docName: 'tpl-1', acknowledgeShared: true });
    submitEdit();
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(edit).toHaveBeenCalledWith('tpl-1', expect.anything(), true);
  });

  it('does not acknowledge for an unshared edit', async () => {
    edit.mockResolvedValue({ success: true, name: 'order_update', edits_left: 2 });
    setup({ initial, docName: 'tpl-1' });
    submitEdit();
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(edit).toHaveBeenCalledWith('tpl-1', expect.anything(), undefined);
  });
});

describe('copy mode', () => {
  const source: TemplateWizardDraft = { ...emptyDraft('UTILITY'), name: 'order_update', language: 'en_US', body: 'Your order shipped' };

  it('opens in create mode prefilled with name_v2 and the source content', async () => {
    draftApi.mockResolvedValue({ success: true, name: 'd1' } as never);
    setup({ copyFrom: source, isAdmin: false });
    expect(screen.getByRole('region', { name: 'Write it' })).toBeInTheDocument();
    const name = screen.getByLabelText('Template name');
    expect(name).toBeEnabled();
    expect(name).toHaveValue('order_update_v2');
    expect(screen.getByRole('combobox', { name: /Language/ })).toBeEnabled();
    expect(screen.getByDisplayValue('Your order shipped')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeInTheDocument();
    next();
    fireEvent.click(screen.getByRole('button', { name: 'Request approval' }));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ kind: 'draft', name: 'd1' }));
    expect(draftApi).toHaveBeenCalledWith('gw', expect.objectContaining({ template_name: 'order_update_v2' }));
    expect(edit).not.toHaveBeenCalled();
  });
});

describe('URL button example', () => {
  it('expands a bare value into the full link when the field loses focus', () => {
    const d = addButton({ ...emptyDraft('UTILITY'), name: 'order_update', language: 'en_US', body: 'Your order shipped' }, 'URL', 'u1');
    setup({ initial: { ...d, buttons: [{ ...d.buttons[0], text: 'Track', url: 'https://example.com/track/{{1}}' }] }, docName: 'tpl-1', editsLeft: 2 });
    const input = screen.getByLabelText('Example link') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'abc123' } });
    fireEvent.blur(input);
    expect(input.value).toBe('https://example.com/track/abc123');
    expect(screen.getByText(/Expanded to the full link: https:\/\/example.com\/track\/abc123/)).toBeInTheDocument();
  });
});
