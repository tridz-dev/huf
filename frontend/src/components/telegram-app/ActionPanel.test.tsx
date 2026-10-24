// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/services/telegramAppApi', async () => {
  const actual = await vi.importActual<typeof import('@/services/telegramAppApi')>('@/services/telegramAppApi');
  return { ...actual, actPrepare: vi.fn(), actConfirm: vi.fn() };
});
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import { actConfirm, actPrepare, TelegramAppError } from '@/services/telegramAppApi';
import { ActionPanel } from './ActionPanel';

const prepare = vi.mocked(actPrepare);
const confirm = vi.mocked(actConfirm);

beforeEach(() => {
  vi.clearAllMocks();
  window.Telegram = { WebApp: { initData: 'x', HapticFeedback: { notificationOccurred: vi.fn() } } };
});

describe('ActionPanel', () => {
  it('prepares, shows the description, then confirms', async () => {
    prepare.mockResolvedValue({
      nonce: 'n1', description: 'Approve PO-1 (Draft to Approved)', expires_in: 300,
      action: { doctype: 'PO', name: 'PO-1', action: 'Approve' },
    });
    confirm.mockResolvedValue({ result: 'Done: PO-1 is now Approved' });
    const onDone = vi.fn();
    render(<ActionPanel doctype="PO" name="PO-1" actions={['Approve', 'Reject']} onDone={onDone} />);

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(await screen.findByText('Approve PO-1 (Draft to Approved)')).toBeInTheDocument();
    expect(confirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(confirm).toHaveBeenCalledWith('n1'));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Done: PO-1 is now Approved'));
    expect(window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred).toHaveBeenCalledWith('success');
    expect(onDone).toHaveBeenCalled();
  });

  it('does not confirm when cancelled and toasts prepare errors', async () => {
    prepare.mockRejectedValueOnce(new TelegramAppError('refused', 'Not allowed', 400));
    render(<ActionPanel doctype="PO" name="PO-1" actions={['Reject']} />);
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Not allowed'));
    expect(confirm).not.toHaveBeenCalled();
  });

  it('renders nothing without actions', () => {
    const { container } = render(<ActionPanel doctype="PO" name="PO-1" actions={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
