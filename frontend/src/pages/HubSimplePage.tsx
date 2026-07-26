import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  Plus, MessageSquare, Bot, Workflow,
  Database, BookOpen, Cpu, LayoutDashboard, Settings, Send,
  PanelLeftClose, PanelLeftOpen,
} from 'lucide-react';
import { useUser } from '@/contexts/UserContext';
import { usePermissions } from '@/contexts/PermissionsContext';
import { IconRail, IconRailButton } from '@/components/IconRail';
import { HubConversationView } from '@/components/hub/HubConversationView';
import { AutoGrowTextarea } from '@/components/hub/AutoGrowTextarea';
import { HubRecentChats } from '@/components/hub/HubRecentChats';
import { SlashCommandMenu } from '@/components/hub/SlashCommandMenu';
import { getHubReadiness, HubReadiness } from '@/services/hubApi';
import { getConversationMessages } from '@/services/chatApi';
import { sendMessage, streamingAvailable } from '@/services/streamChatApi';

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

const NAV_ITEMS = [
  { icon: MessageSquare, label: 'Home', path: '/' },
  { icon: Bot, label: 'Agents', path: '/agents' },
  { icon: Workflow, label: 'Flows', path: '/flows' },
  { icon: Database, label: 'Executions', path: '/executions' },
  { icon: BookOpen, label: 'Knowledge', path: '/knowledge' },
  { icon: Cpu, label: 'AI Providers', path: '/models' },
];

const RAIL_VISIBLE_KEY = 'hub:rail-visible';

function readRailVisible(): boolean {
  try {
    return localStorage.getItem(RAIL_VISIBLE_KEY) !== 'false';
  } catch {
    return true;
  }
}

export default function HubSimplePage() {
  const navigate = useNavigate();
  const { user } = useUser();
  const { hufRole } = usePermissions();

  const role =
    hufRole === 'Huf Admin' ? 'admin'
    : hufRole === 'Huf Manager' || hufRole === 'Huf User' ? 'builder'
    : 'viewer';

  const initials = (user?.full_name || user?.name || 'U')
    .split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2);

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
  const [railVisible, setRailVisible] = useState<boolean>(readRailVisible);

  const toggleRail = () => {
    setRailVisible(prev => {
      const next = !prev;
      try {
        localStorage.setItem(RAIL_VISIBLE_KEY, String(next));
      } catch {
        void 0;
      }
      return next;
    });
  };

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

  const handleSwitchToAdvanced = () => {
    navigate('/dashboard');
  };

  return (
    <div className="h-screen flex bg-paper overflow-hidden">
      {/* Collapsed rail — same 48px look as the dashboard's collapsed sidebar */}
      <motion.div
        initial={false}
        animate={{ width: railVisible ? 48 : 0 }}
        transition={{ duration: 0.2, ease: 'easeInOut' }}
        className="flex flex-shrink-0 overflow-hidden"
      >
        <IconRail
          header={
            /* Matches AppSidebarHeader's collapsed mark (signal square) */
            <div className="flex items-center gap-2 px-2 py-3">
              <span className="inline-block w-2 h-2 bg-signal flex-shrink-0" />
            </div>
          }
          actions={
            <>
              <IconRailButton icon={Plus} label="New chat" onClick={handleNewChat} />
              <HubRecentChats onSelect={handleLoadConversation} />
            </>
          }
          items={NAV_ITEMS.map((item, i) => ({
            key: item.label,
            icon: item.icon,
            label: item.label,
            active: i === 0,
            onClick: () => navigate(item.path),
          }))}
          footer={
            <>
              <IconRailButton
                icon={LayoutDashboard}
                label="Switch to Advanced Hub"
                onClick={handleSwitchToAdvanced}
              />
              <IconRailButton
                icon={Settings}
                label="Settings"
                onClick={() => navigate('/models')}
              />
            </>
          }
        />
      </motion.div>

      {/* Rail hide/show toggle — stays visible when the rail is hidden */}
      <button
        onClick={toggleRail}
        title={railVisible ? 'Hide sidebar' : 'Show sidebar'}
        aria-label={railVisible ? 'Hide sidebar' : 'Show sidebar'}
        className={`fixed top-3 z-50 flex size-7 items-center justify-center rounded-sm border border-line bg-panel text-steel shadow-sm hover:border-steel-soft hover:text-ink transition-all duration-200 ${
          railVisible ? 'left-[60px]' : 'left-3'
        }`}
      >
        {railVisible ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeftOpen className="w-4 h-4" />}
      </button>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-full relative overflow-hidden">
        {/* User avatar top-right */}
        <div className="absolute top-3 right-4 z-10">
          <div className="w-7 h-7 rounded-full bg-ink flex items-center justify-center text-paper text-xs font-medium">
            {initials}
          </div>
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
                  <h1 className="font-display font-bold text-2xl uppercase tracking-wide text-ink text-center">
                    What can I do for you.
                  </h1>
                </div>

                {/* Input composer */}
                <div className="w-full max-w-2xl relative">
                  <SlashCommandMenu isVisible={showSlashMenu} query={slashQuery} onSelect={handleSlashSelect} />
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
                    <button
                      onClick={handleSend}
                      disabled={!inputValue.trim()}
                      className="absolute right-3 bottom-3 p-1.5 rounded-md bg-ink text-paper disabled:bg-paper-deep disabled:text-steel-soft hover:bg-signal transition-colors"
                    >
                      <Send className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Starter prompts */}
                  <motion.div
                    animate={{ opacity: showSlashMenu ? 0 : 1 }}
                    transition={{ duration: 0.15 }}
                    className="mt-5 grid grid-cols-2 gap-2"
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
