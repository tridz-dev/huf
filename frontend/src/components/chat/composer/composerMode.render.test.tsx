// @vitest-environment jsdom
// The composer follows the agent's modality: text only hides dictation and the call button, voice
// only hides the textarea, text and voice is unchanged.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/services/streamChatApi', () => ({ sendMessage: vi.fn(), streamingAvailable: true, setStreamingAvailable: vi.fn() }));
vi.mock('@/services/chatApi', () => ({ transcribeAudio: vi.fn(), prepareMessageWithFile: vi.fn(), uploadFileAttachment: vi.fn() }));
vi.mock('@/lib/clientToolDispatcher', () => ({ executeClientToolCallsFromResponse: vi.fn() }));
vi.mock('@/components/ai-elements/speech-input', () => ({ SpeechInput: () => <button aria-label="Dictate" /> }));
vi.mock('@/hooks/useVoiceCall', () => ({ useVoiceCall: () => ({ status: 'idle', error: null, start: vi.fn(), stop: vi.fn() }) }));
vi.mock('../VoiceCallOverlay', () => ({ VoiceCallOverlay: () => null }));
vi.mock('../useChatAgentIdentity', () => ({ cacheAgentNameForChat: vi.fn() }));
vi.mock('../chatMessageList.mappers', () => ({ cacheReasoning: vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('@/hooks/useDesktopHosts', () => ({ refreshDesktopHosts: vi.fn() }));

import { ChatInput } from '../ChatInput';
import { publishComposerMode, resetComposerModes } from './composerMode';

function mount(agentName: string) {
  return render(
    <MemoryRouter>
      <ChatInput
        chatId="c1"
        agentName={agentName}
        onStatusChange={vi.fn()}
        isCreatingConversationRef={{ current: false }}
        newlyCreatedConversationIdRef={{ current: null }}
        setMessages={vi.fn()}
      />
    </MemoryRouter>,
  );
}

const state = () => ({
  textarea: !!screen.queryByPlaceholderText('Write a message…'),
  call: !!screen.queryByLabelText('Talk to this agent'),
  mic: !!screen.queryByLabelText('Dictate'),
});

describe('ChatInput modality', () => {
  afterEach(() => {
    cleanup();
    act(() => resetComposerModes());
  });

  it('text only: no call button and no dictation', () => {
    publishComposerMode('T', { agent_modality: 'Both', voice_enabled: 0 });
    mount('T');
    expect(state()).toEqual({ textarea: true, call: false, mic: false });
  });

  it('voice only: no textarea, call and dictation available', () => {
    publishComposerMode('V', { agent_modality: 'Voice', voice_enabled: 1 });
    mount('V');
    expect(state()).toEqual({ textarea: false, call: true, mic: true });
  });

  it('text and voice: unchanged, and switching agents updates without reload', () => {
    publishComposerMode('B', { agent_modality: 'Both', voice_enabled: 1 });
    publishComposerMode('T', { agent_modality: 'Text', voice_enabled: 1 });
    const { rerender } = mount('B');
    expect(state()).toEqual({ textarea: true, call: true, mic: true });
    rerender(
      <MemoryRouter>
        <ChatInput chatId="c1" agentName="T" onStatusChange={vi.fn()} isCreatingConversationRef={{ current: false }} newlyCreatedConversationIdRef={{ current: null }} setMessages={vi.fn()} />
      </MemoryRouter>,
    );
    expect(state()).toEqual({ textarea: true, call: false, mic: false });
  });
});
