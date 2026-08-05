import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { Plus, Send } from 'lucide-react';
import { usePermissions } from '@/contexts/PermissionsContext';
import { IconRailButton } from '@/components/IconRail';
import { HubConversationView } from '@/components/hub/HubConversationView';
import { AutoGrowTextarea } from '@/components/hub/AutoGrowTextarea';
import { HubRecentChats } from '@/components/hub/HubRecentChats';
import { SlashCommandMenu } from '@/components/hub/SlashCommandMenu';
import { Button } from '@/components/ui/button';
import { getHubReadiness, HubReadiness } from '@/services/hubApi';
import { getConversationMessages } from '@/services/chatApi';
import { sendMessage, streamingAvailable } from '@/services/streamChatApi';
import {
  isSceneryEnabled,
  getSceneryOpacity,
  SCENERY_IMAGE_URL,
} from '@/lib/personalization';

interface Message { role: 'user' | 'assistant'; content: string; _key?: string; }

interface StarterPrompt {
  label: string;
  route?: string;
  message?: string;
}

const STARTER_PROMPTS: Record<string, StarterPrompt[]> = {
  admin: [
    { label: 'Create approval flow for ToDo', route: '/flows' },
    { label: 'Invite user and assign Builder role', route: '/users' },
    { label: 'Show weekly cost analysis', route: '/dashboard' },
    { label: 'List failed automations today', route: '/executions' },
  ],
  builder: [
    { label: 'Build a new flow', route: '/flows' },
    { label: 'Create a new knowledge agent', route: '/agents' },
    { label: 'Browse existing agents', route: '/agents' },
    { label: 'Add an agent tool', route: '/agents' },
  ],
  viewer: [
    { label: 'Show dashboard metrics', route: '/dashboard' },
    { label: 'List active agents', route: '/agents' },
    { label: 'View flow success rates', route: '/executions' },
    { label: 'Generate cost report', route: '/dashboard' },
  ],
};

export default function HubSimplePage() {
  const navigate = useNavigate();
  const { hufRole } = usePermissions();

  const role =
    hufRole === 'Huf Admin' ? 'admin'
    : hufRole === 'Huf Manager' || hufRole === 'Huf User' ? 'builder'
    : 'viewer';

  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [slashQuery, setSlashQuery] = useState('');
  const [isInputFocused, setIsInputFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [hasProvider, setHasProvider] = useState<boolean | null>(null);
  const [readiness, setReadiness] = useState<HubReadiness | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [isStreaming, setIsStreaming] = useState(false);
  const [scenery, setScenery] = useState(false);
  const [sceneryOpacity, setSceneryOpacity] = useState(100);

  // Load scenery preference from localStorage on mount and on cross-tab changes
  useEffect(() => {
    const update = () => {
      setScenery(isSceneryEnabled());
      setSceneryOpacity(getSceneryOpacity());
    };
    update();
    window.addEventListener('storage', update);
    return () => window.removeEventListener('storage', update);
  }, []);

  // Detect slash commands
  useEffect(() => {
    const lastSlash = inputValue.lastIndexOf('/');
    if (lastSlash !== -1) {
      const after = inputValue.slice(lastSlash + 1);
      if (!after.includes(' ')) {
        setSlashQuery(after);
        setShowSlashMenu(true);
        return;
      }
    }
    setShowSlashMenu(false);
  }, [inputValue]);

  // Check hub readiness on mount
  useEffect(() => {
    getHubReadiness().then(result => {
      setReadiness(result);
      setHasProvider(result.ready);
    }).catch(() => setHasProvider(false));
  }, []);

  const sendToAgent = async (msg: string) => {
    if (!hasProvider) {
      setTimeout(() => {
        setMessages(prev => [...prev, { role: 'assistant', content: '__NO_PROVIDER__' }]);
      }, 300);
      return;
    }

    // Optimistically insert empty assistant message — same pattern as ChatInput
    const assistantKey = `assistant-${Date.now()}`;
    setMessages(prev => [...prev, { role: 'assistant', content: '', _key: assistantKey }]);
    setIsStreaming(true);

    const updateAssistantContent = (content: string) => {
      setMessages(prev => prev.map((m) =>
        m._key === assistantKey ? { ...m, content } : m
      ));
    };

    try {
      const useStream = streamingAvailable;
      const result = await sendMessage(
        { agent: 'Hub Orchestrator', message: msg, conversationId },
        { useStreaming: useStream, onDelta: useStream ? updateAssistantContent : undefined }
      );
      const message = result.message as {
        response?: string;
        conversation_id?: string;
        run?: { response?: string; conversation_id?: string };
      };
      const responseText: string =
        message.run?.response ?? message.response ?? "I've processed your request.";
      const newConvId: string =
        message.run?.conversation_id ?? message.conversation_id ?? '';
      if (!useStream) updateAssistantContent(responseText);
      setConversationId(newConvId || undefined);
    } catch {
      updateAssistantContent("Hub Orchestrator agent is not configured yet. Go to Agents to set one up.");
    } finally {
      setIsStreaming(false);
    }
  };

  const handleSend = () => {
    if (!inputValue.trim()) return;
    const msg = inputValue.trim();
    setInputValue('');
    setShowSlashMenu(false);
    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    sendToAgent(msg);
  };

  // Send an explicit string (e.g. an ask-user card answer) without touching the input state
  const sendText = (text: string) => {
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    sendToAgent(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !showSlashMenu) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSlashSelect = (cmd: string) => {
    const routeMap: Record<string, string> = {
      '/flow': '/flows', '/agent': '/agents', '/users': '/users',
      '/runs': '/executions', '/knowledge': '/knowledge', '/settings': '/models', '/cost': '/dashboard',
    };
    const lastSlash = inputValue.lastIndexOf('/');
    setInputValue(inputValue.slice(0, lastSlash) + cmd + ' ');
    setShowSlashMenu(false);
    textareaRef.current?.focus();
    // Navigate if it's a pure command (nothing before slash)
    if (lastSlash === 0 || lastSlash === -1) {
      const route = routeMap[cmd];
      if (route) { navigate(route); return; }
    }
  };

  const handlePromptClick = (prompt: StarterPrompt) => {
    if (prompt.route) {
      navigate(prompt.route);
      return;
    }
    const msg = prompt.message || prompt.label;
    setMessages([{ role: 'user', content: msg }]);
    sendToAgent(msg);
  };

  const handleNewChat = () => {
    setMessages([]);
    setInputValue('');
    setShowSlashMenu(false);
    setConversationId(undefined);
  };

  // Leave the conversation view back to the hub greeting without destroying
  // the conversation — conversationId is preserved so the chat stays
  // resumable via the HubRecentChats flyout.
  const handleGoHome = () => {
    setMessages([]);
    setInputValue('');
    setShowSlashMenu(false);
    setSlashQuery('');
  };

  // Resume a previous Hub Orchestrator conversation picked from HubRecentChats
  const handleLoadConversation = async (id: string) => {
    const res = await getConversationMessages({ conversation: id, limit: 100 });
    const loaded: Message[] = (res?.data ?? []).map(m => ({
      role: m.isAgent ? 'assistant' : 'user',
      content: m.content,
      _key: m.id,
    }));
    setMessages(loaded);
    setConversationId(id);
  };

  return (
    <div className="h-full flex bg-paper overflow-hidden relative">
      {scenery && (
        <div
          aria-hidden="true"
          className="absolute inset-0 z-0"
          style={{
            backgroundImage: `url(${SCENERY_IMAGE_URL})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            backgroundRepeat: 'no-repeat',
            opacity: sceneryOpacity / 100,
          }}
        />
      )}
      {/* Main Content — sidebar, header and user avatar are provided by
          UnifiedLayout/AppSidebar so the Hub matches the rest of the app. */}
      <main className="relative z-10 flex-1 flex flex-col h-full overflow-hidden">
        {/* Chat toolbar — new chat / resume a recent conversation */}
        <div className="absolute top-3 left-4 z-10 flex items-center gap-1">
          <IconRailButton icon={Plus} label="New chat" onClick={handleNewChat} />
          <HubRecentChats onSelect={handleLoadConversation} />
        </div>

        <AnimatePresence mode="wait">
          {messages.length === 0 ? (
            <motion.div
              key="home"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, y: 24 }}
              transition={{ duration: 0.2 }}
              className="flex-1 flex flex-col"
            >
              {/* Composer stays centered — focusing must not move it */}
              <div className="absolute inset-x-0 bottom-0 top-0 flex flex-col items-center justify-center px-4">
                {/* Greeting */}
                <div className="mb-8">
                  <h1 className="font-display font-bold text-2xl tracking-wide text-ink text-center">
                    What can huf do for you today?
                  </h1>
                </div>

                {/* Input composer */}
                <div className="w-full max-w-2xl">
                  <div className={`relative bg-panel border transition-all duration-200 ${
                    isInputFocused ? 'rounded-xl border-signal' : 'rounded-xl border-line hover:border-steel-soft'
                  }`}>
                    <AutoGrowTextarea
                      ref={textareaRef}
                      value={inputValue}
                      onChange={e => setInputValue(e.target.value)}
                      onKeyDown={handleKeyDown}
                      onFocus={() => setIsInputFocused(true)}
                      onBlur={() => setTimeout(() => setIsInputFocused(false), 150)}
                      placeholder="Ask anything or type / for commands..."
                      className="w-full px-4 py-3 pr-12 text-sm resize-none outline-none bg-transparent text-ink placeholder:text-steel-soft min-h-[52px]"
                    />
                    <Button
                      onClick={handleSend}
                      disabled={!inputValue.trim()}
                      variant="ghost"
                      size="icon-sm"
                      className="absolute right-3 bottom-3 rounded-md bg-ink text-paper disabled:bg-paper-deep disabled:text-steel-soft hover:bg-signal hover:text-paper"
                    >
                      <Send className="w-3.5 h-3.5" />
                    </Button>
                    <SlashCommandMenu isVisible={showSlashMenu} query={slashQuery} onSelect={handleSlashSelect} />
                  </div>

                  {/* Starter prompts */}
                  <motion.div
                    animate={{ opacity: showSlashMenu ? 0 : 1 }}
                    transition={{ duration: 0.15 }}
                    className={`mt-5 grid grid-cols-2 gap-2 ${showSlashMenu ? 'pointer-events-none' : ''}`}
                  >
                    {(STARTER_PROMPTS[role] || STARTER_PROMPTS.admin).map((prompt, i) => (
                      <motion.button
                        key={prompt.label}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.05 + i * 0.05 }}
                        onClick={() => handlePromptClick(prompt)}
                        className="p-3 text-left rounded-lg border border-line hover:border-steel-soft hover:bg-paper-deep transition-all group"
                      >
                        <p className="text-xs text-steel group-hover:text-ink transition-colors line-clamp-2">{prompt.label}</p>
                      </motion.button>
                    ))}
                  </motion.div>
                </div>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="conversation"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex-1 flex flex-col min-h-0 pt-10"
            >
              <HubConversationView
                messages={messages}
                inputValue={inputValue}
                setInputValue={setInputValue}
                onSend={handleSend}
                showSlashMenu={showSlashMenu}
                slashQuery={slashQuery}
                onSlashSelect={handleSlashSelect}
                onNewChat={handleNewChat}
                onHome={handleGoHome}
                onSendText={sendText}
                isStreaming={isStreaming}
                remediation={readiness?.remediation}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
