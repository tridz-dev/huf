import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  Plus, MessageSquare, Bot, Workflow,
  Database, BookOpen, Cpu, LayoutDashboard, Settings, Send,
} from 'lucide-react';
import { useUser } from '@/contexts/UserContext';
import { usePermissions } from '@/contexts/PermissionsContext';
import { HubConversationView } from '@/components/hub/HubConversationView';
import { SlashCommandMenu } from '@/components/hub/SlashCommandMenu';
import { getProviders } from '@/services/providerApi';
import { sendMessage, streamingAvailable } from '@/services/streamChatApi';

interface Message { role: 'user' | 'assistant'; content: string; }

interface StarterPrompt {
  label: string;
  route?: string;
  message?: string;
}

const GREETINGS: Record<string, string> = {
  admin: 'What would you like to orchestrate?',
  builder: 'What are you building today?',
  operator: 'What do you need to monitor?',
  viewer: 'What insights are you looking for?',
};

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
  operator: [
    { label: 'Show failed executions', route: '/executions' },
    { label: 'View all executions', route: '/executions' },
    { label: 'View dashboard metrics', route: '/dashboard' },
    { label: 'Export run diagnostics', route: '/executions' },
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

export default function HubSimplePage() {
  const navigate = useNavigate();
  const { user } = useUser();
  const { capabilities } = usePermissions();

  const role = capabilities.includes('system.admin') ? 'admin'
    : capabilities.includes('agent.use') ? 'builder'
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
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [isStreaming, setIsStreaming] = useState(false);

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

  // Check providers on mount
  useEffect(() => {
    getProviders({ limit: 1 }).then(result => {
      const items = Array.isArray(result) ? result : result.items;
      setHasProvider(items.length > 0);
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
    setMessages(prev => [...prev, { role: 'assistant', content: '', _key: assistantKey } as any]);
    setIsStreaming(true);

    const updateAssistantContent = (content: string) => {
      setMessages(prev => prev.map((m: any) =>
        m._key === assistantKey ? { ...m, content } : m
      ));
    };

    try {
      const useStream = streamingAvailable;
      const result = await sendMessage(
        { agent: 'Hub Orchestrator', message: msg, conversationId },
        { useStreaming: useStream, onDelta: useStream ? updateAssistantContent : undefined }
      );
      const data = result.message as any;
      const responseText: string = data?.run?.response ?? data?.response ?? "I've processed your request.";
      const newConvId: string = data?.conversation_id ?? data?.run?.conversation_id ?? '';
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !showSlashMenu) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSlashSelect = (cmd: string) => {
    const routeMap: Record<string, string> = {
      '/flow': '/flows', '/agent': '/agents', '/users': '/users',
      '/runs': '/executions', '/knowledge': '/knowledge', '/settings': '/models', '/cost': '/',
    };
    const lastSlash = inputValue.lastIndexOf('/');
    setInputValue(inputValue.slice(0, lastSlash) + cmd + ' ');
    setShowSlashMenu(false);
    textareaRef.current?.focus();
    // Navigate if it's a pure command (nothing before slash)
    if (lastSlash === 0 || lastSlash === -1) {
      const route = routeMap[cmd];
      if (route && route !== '/') { navigate(route); return; }
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
  };

  const handleSwitchToAdvanced = () => {
    navigate('/dashboard');
  };

  return (
    <div className="min-h-screen flex bg-white">
      {/* Collapsed Sidebar */}
      <aside className="w-[60px] bg-white border-r border-slate-100 flex flex-col py-3 flex-shrink-0">
        {/* Logo */}
        <div className="px-3 mb-4">
          <div className="w-9 h-9 rounded-lg bg-violet-600 flex items-center justify-center">
            <span className="text-white text-xs font-bold">H</span>
          </div>
        </div>

        {/* New chat */}
        <div className="px-2 mb-3">
          <button
            onClick={handleNewChat}
            title="New chat"
            className="w-10 h-10 rounded-lg border border-slate-200 flex items-center justify-center text-slate-500 hover:border-violet-300 hover:text-violet-600 hover:bg-violet-50 transition-all"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 space-y-1">
          {NAV_ITEMS.map((item, i) => (
            <button
              key={item.label}
              title={item.label}
              onClick={() => navigate(item.path)}
              className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${
                i === 0 ? 'bg-violet-100 text-violet-700' : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
              }`}
            >
              <item.icon className="w-4 h-4" />
            </button>
          ))}
        </nav>

        {/* Bottom actions */}
        <div className="px-2 pt-3 border-t border-slate-100 space-y-1">
          <button
            onClick={handleSwitchToAdvanced}
            title="Switch to Advanced Hub"
            className="w-10 h-10 flex items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
          >
            <LayoutDashboard className="w-4 h-4" />
          </button>
          <button
            onClick={() => navigate('/models')}
            title="Settings"
            className="w-10 h-10 flex items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-h-screen relative overflow-hidden">
        {/* User avatar top-right */}
        <div className="absolute top-3 right-4 z-10">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-500 to-purple-500 flex items-center justify-center text-white text-xs font-medium">
            {initials}
          </div>
        </div>

        <AnimatePresence mode="wait">
          {messages.length === 0 ? (
            <motion.div
              key="home"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex-1 flex flex-col"
            >
              <motion.div
                className="absolute inset-x-0 bottom-0 top-0 flex flex-col items-center px-4"
                animate={{
                  justifyContent: isInputFocused ? 'flex-start' : 'center',
                  paddingTop: isInputFocused ? '80px' : '0px',
                }}
                transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
              >
                {/* Greeting */}
                <motion.div
                  animate={{ opacity: isInputFocused ? 0 : 1, height: isInputFocused ? 0 : 'auto', marginBottom: isInputFocused ? 0 : 32 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <h1 className="text-2xl font-medium text-slate-800 text-center">
                    {GREETINGS[role] || GREETINGS.admin}
                  </h1>
                </motion.div>

                {/* Input composer */}
                <div className="w-full max-w-2xl relative">
                  <SlashCommandMenu isVisible={showSlashMenu} query={slashQuery} onSelect={handleSlashSelect} />
                  <div className={`relative bg-white border transition-all duration-200 ${
                    isInputFocused ? 'rounded-xl border-violet-400 shadow-lg shadow-violet-100' : 'rounded-xl border-slate-200 shadow-sm hover:border-slate-300'
                  }`}>
                    <textarea
                      ref={textareaRef}
                      value={inputValue}
                      onChange={e => setInputValue(e.target.value)}
                      onKeyDown={handleKeyDown}
                      onFocus={() => setIsInputFocused(true)}
                      onBlur={() => setTimeout(() => setIsInputFocused(false), 150)}
                      placeholder="Ask anything or type / for commands..."
                      rows={1}
                      className="w-full px-4 py-3 pr-12 text-sm resize-none outline-none bg-transparent text-slate-700 placeholder:text-slate-400 min-h-[52px]"
                    />
                    <button
                      onClick={handleSend}
                      disabled={!inputValue.trim()}
                      className="absolute right-3 bottom-3 p-1.5 rounded-md bg-violet-600 text-white disabled:bg-slate-200 disabled:text-slate-400 hover:bg-violet-700 transition-colors"
                    >
                      <Send className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Starter prompts */}
                  <motion.div
                    animate={{ opacity: showSlashMenu ? 0 : (isInputFocused ? 0.4 : 1) }}
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
                        className="p-3 text-left rounded-lg border border-slate-200 hover:border-violet-300 hover:bg-violet-50/40 transition-all group"
                      >
                        <p className="text-xs text-slate-600 group-hover:text-violet-700 transition-colors line-clamp-2">{prompt.label}</p>
                      </motion.button>
                    ))}
                  </motion.div>
                </div>
              </motion.div>
            </motion.div>
          ) : (
            <motion.div
              key="conversation"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex-1 flex flex-col h-full pt-10"
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
                isStreaming={isStreaming}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
