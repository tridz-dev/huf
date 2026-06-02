import { useRef, useEffect } from 'react';
import { motion } from 'motion/react';
import { Send, Sparkles, Plus } from 'lucide-react';
import { useUser } from '@/contexts/UserContext';
import { SlashCommandMenu } from './SlashCommandMenu';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface HubConversationViewProps {
  messages: Message[];
  inputValue: string;
  setInputValue: (v: string) => void;
  onSend: () => void;
  showSlashMenu: boolean;
  slashQuery: string;
  onSlashSelect: (cmd: string) => void;
  onNewChat: () => void;
  isStreaming?: boolean;
}

export function HubConversationView({
  messages, inputValue, setInputValue, onSend,
  showSlashMenu, slashQuery, onSlashSelect, onNewChat,
  isStreaming,
}: HubConversationViewProps) {
  const { user } = useUser();
  const scrollRef = useRef<HTMLDivElement>(null);

  const initials = (user?.full_name || user?.name || 'U')
    .split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !showSlashMenu) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.map((msg, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
            className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
          >
            <div className="flex-shrink-0">
              {msg.role === 'user' ? (
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-500 to-purple-500 flex items-center justify-center text-white text-xs font-medium">
                  {initials}
                </div>
              ) : (
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center">
                  <Sparkles className="w-3.5 h-3.5 text-white" />
                </div>
              )}
            </div>
            <div className={`flex-1 ${msg.role === 'user' ? 'text-right' : ''}`}>
              {msg.role === 'assistant' && (
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-xs font-medium text-violet-700">Hub Orchestrator</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-50 text-violet-600 border border-violet-100">System</span>
                </div>
              )}
              {msg.content === '__NO_PROVIDER__' ? (
                <div className="inline-block max-w-[85%] px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-left">
                  <p className="text-sm font-medium text-amber-800 mb-1">No AI Provider configured</p>
                  <p className="text-xs text-amber-700 mb-3">Add a provider and model to start using Hub Orchestrator.</p>
                  <a href="/huf/models" className="text-xs px-3 py-1.5 rounded-lg bg-violet-600 text-white hover:bg-violet-700 transition-colors inline-block">
                    Add Provider →
                  </a>
                </div>
              ) : (
                <div className={`inline-block max-w-[85%] px-3 py-2 rounded-xl text-sm text-left ${
                  msg.role === 'user' ? 'bg-violet-600 text-white' : 'bg-slate-100 text-slate-700'
                }`}>
                  {msg.content}
                </div>
              )}
            </div>
          </motion.div>
        ))}

        {/* Typing indicator */}
        {(messages.length > 0 && messages[messages.length - 1].role === 'user') || isStreaming ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center">
              <Sparkles className="w-3.5 h-3.5 text-white" />
            </div>
            <div className="flex items-center gap-1 px-3 py-2 bg-slate-100 rounded-xl">
              {[0, 0.15, 0.3].map((delay, i) => (
                <motion.div key={i} animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 0.6, repeat: Infinity, delay }} className="w-1.5 h-1.5 rounded-full bg-violet-400" />
              ))}
            </div>
          </motion.div>
        ) : null}
      </div>

      {/* Input */}
      <div className="px-4 py-4 border-t border-slate-100 bg-white">
        <div className="max-w-2xl mx-auto relative">
          <SlashCommandMenu isVisible={showSlashMenu} query={slashQuery} onSelect={onSlashSelect} />
          <div className={`relative bg-white border transition-all rounded-xl ${
            showSlashMenu ? 'border-violet-400' : 'border-slate-200 shadow-sm hover:border-slate-300 focus-within:border-violet-400'
          }`}>
            <textarea
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Continue the conversation..."
              rows={1}
              className="w-full px-4 py-3 pr-24 text-sm resize-none outline-none bg-transparent text-slate-700 placeholder:text-slate-400 min-h-[52px]"
            />
            <div className="absolute right-2 bottom-2 flex items-center gap-1">
              <button onClick={onNewChat} className="p-1.5 rounded-md text-slate-400 hover:text-violet-600 hover:bg-violet-50 transition-colors" title="New chat">
                <Plus className="w-4 h-4" />
              </button>
              <button onClick={onSend} disabled={!inputValue.trim()} className="p-1.5 rounded-md bg-violet-600 text-white disabled:bg-slate-200 disabled:text-slate-400 hover:bg-violet-700 transition-colors">
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
