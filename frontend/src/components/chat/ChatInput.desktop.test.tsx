// @vitest-environment jsdom
//
// Composer behaviour for desktop-hosted conversations: a run the server declines with a structured
// desktop failure becomes a banner (not a failed-run card), the typed text comes back, and Retry /
// Rebind resend it.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { createRef } from 'react';

const sendMessage = vi.fn();
vi.mock('@/services/streamChatApi', () => ({
  sendMessage: (...a: unknown[]) => sendMessage(...a),
  streamingAvailable: true,
  setStreamingAvailable: vi.fn(),
}));
vi.mock('@/services/chatApi', () => ({
  transcribeAudio: vi.fn(),
  prepareMessageWithFile: vi.fn(),
  uploadFileAttachment: vi.fn(),
}));
vi.mock('@/lib/clientToolDispatcher', () => ({ executeClientToolCallsFromResponse: vi.fn() }));
vi.mock('@/components/ai-elements/speech-input', () => ({ SpeechInput: () => null }));
vi.mock('@/hooks/useVoiceCall', () => ({
  useVoiceCall: () => ({ status: 'idle', error: null, start: vi.fn(), end: vi.fn() }),
}));
vi.mock('./VoiceCallOverlay', () => ({ VoiceCallOverlay: () => null }));
vi.mock('./useChatAgentIdentity', () => ({ cacheAgentNameForChat: vi.fn() }));
vi.mock('./chatMessageList.mappers', () => ({ cacheReasoning: vi.fn() }));
const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (...a: unknown[]) => toastError(...a), success: (...a: unknown[]) => toastSuccess(...a) } }));

const rebind = vi.fn();
vi.mock('@/services/desktopHostApi', async () => {
  const actual = await vi.importActual<typeof import('@/services/desktopHostApi')>('@/services/desktopHostApi');
  return { ...actual, rebindDesktopConversation: (...a: unknown[]) => rebind(...a) };
});
vi.mock('@/hooks/useDesktopHosts', () => ({ refreshDesktopHosts: vi.fn().mockResolvedValue(undefined), useDesktopHosts: () => ({ hosts: [], byDevice: new Map(), loaded: true, error: false, refresh: vi.fn() }) }));

import { ChatInput, type ChatInputHandle } from './ChatInput';
import type { MessageType } from './types';

function setup(props: Partial<React.ComponentProps<typeof ChatInput>> = {}) {
  let messages: MessageType[] = [];
  const setMessages = vi.fn((update: React.SetStateAction<MessageType[]>) => {
    messages = typeof update === 'function' ? update(messages) : update;
  });
  const onStatusChange = vi.fn();
  const ref = createRef<ChatInputHandle>();
  render(
    <MemoryRouter>
      <ChatInput
        ref={ref}
        chatId="conv-1"
        agentName="Dev Agent"
        runImmediately
        hostedDeviceId="dev1"
        onStatusChange={onStatusChange}
        isCreatingConversationRef={{ current: false }}
        newlyCreatedConversationIdRef={{ current: null }}
        setMessages={setMessages}
        {...props}
      />
    </MemoryRouter>,
  );
  return { getMessages: () => messages, onStatusChange };
}

const offline = {
  message: {
    success: false,
    queued: false,
    error: 'desktop_offline',
    code: 'desktop_offline',
    message: 'Laptop is offline.',
    conversation_id: 'conv-1',
    last_seen: Date.now() - 2 * 60_000,
    host_device_id: 'dev1',
    host_label: 'Laptop - repo',
  },
};
const ok = { message: { success: true, queued: true, status: 'Queued', conversation_id: 'conv-1', agent_run_id: 'run-1', sequence: 1 } };

async function typeAndSend(text: string) {
  const box = screen.getByPlaceholderText(/Write a message/);
  await userEvent.type(box, text);
  await userEvent.keyboard('{Enter}');
  return box as HTMLTextAreaElement;
}

beforeEach(() => {
  sendMessage.mockReset();
  rebind.mockReset();
  toastError.mockReset();
  toastSuccess.mockReset();
});

describe('ChatInput with a desktop-hosted conversation', () => {
  it('shows the offline banner with last seen, restores the text, and keeps optimistic bubbles out', async () => {
    sendMessage.mockResolvedValueOnce(offline);
    const { getMessages, onStatusChange } = setup();
    const box = await typeAndSend('list the files');
    const banner = await screen.findByTestId('desktop-run-banner');
    expect(banner).toHaveAttribute('data-code', 'desktop_offline');
    expect(banner).toHaveTextContent('Laptop - repo is offline');
    expect(banner).toHaveTextContent('Last seen 2 min ago');
    expect(box.value).toBe('list the files');
    expect(getMessages()).toEqual([]);
    expect(onStatusChange).toHaveBeenLastCalledWith('ready');
    expect(toastError).not.toHaveBeenCalled();
  });

  it('never streams a hosted turn, even when the agent runs immediately', async () => {
    sendMessage.mockResolvedValueOnce(ok);
    setup();
    await typeAndSend('hi');
    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    expect(sendMessage.mock.calls[0][1]).toMatchObject({ useStreaming: false });
  });

  it('Retry sends the same text again and clears the banner on success', async () => {
    sendMessage.mockResolvedValueOnce(offline).mockResolvedValueOnce(ok);
    setup();
    await typeAndSend('list the files');
    await userEvent.click(await screen.findByRole('button', { name: /Retry/ }));
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(2));
    expect(sendMessage.mock.calls[1][0]).toMatchObject({ message: 'list the files', conversationId: 'conv-1' });
    await waitFor(() => expect(screen.queryByTestId('desktop-run-banner')).toBeNull());
  });

  it('workspace_changed offers a rebind, then resends', async () => {
    sendMessage
      .mockResolvedValueOnce({ message: { success: false, code: 'workspace_changed', error: 'workspace_changed', message: 'x' } })
      .mockResolvedValueOnce(ok);
    rebind.mockResolvedValue({ ok: true, hostLabel: 'Laptop - other' });
    setup();
    await typeAndSend('go');
    await userEvent.click(await screen.findByRole('button', { name: 'Rebind and retry' }));
    await waitFor(() => expect(rebind).toHaveBeenCalledWith('conv-1'));
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(2));
    expect(toastSuccess).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId('desktop-run-banner')).toBeNull());
  });

  it('a refused rebind keeps the banner and explains why', async () => {
    sendMessage.mockResolvedValueOnce({ message: { success: false, code: 'workspace_changed', message: 'x' } });
    rebind.mockResolvedValue({ ok: false, error: { code: 'run_in_progress', message: 'wait' } });
    setup();
    await typeAndSend('go');
    await userEvent.click(await screen.findByRole('button', { name: 'Rebind and retry' }));
    expect(await screen.findByText(/A turn is still running/)).toBeInTheDocument();
    expect(sendMessage).toHaveBeenCalledTimes(1);
  });

  it('remote_disabled by the agent explains and links to the agent settings', async () => {
    sendMessage.mockResolvedValueOnce({
      message: { success: false, code: 'remote_disabled', error: 'remote_disabled', message: 'x', disabled_by: 'agent' },
    });
    setup();
    await typeAndSend('go');
    expect(await screen.findByText('This agent does not allow remote control')).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', '/agents/Dev%20Agent#permissions');
  });

  it('an ordinary failure still becomes a failed-run card, not a desktop banner', async () => {
    sendMessage.mockResolvedValueOnce({ message: { success: false, error: 'Model quota exceeded' } });
    const { getMessages } = setup();
    await typeAndSend('go');
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(screen.queryByTestId('desktop-run-banner')).toBeNull();
    expect(getMessages().some((m) => m.error === 'Model quota exceeded')).toBe(true);
  });
});
