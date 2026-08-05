import { useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import { Send, Sparkles, Plus, Home } from 'lucide-react';
import { useUser } from '@/contexts/UserContext';
import { SlashCommandMenu } from './SlashCommandMenu';
import { HubAskUser, splitAskUserBlocks } from './HubAskUser';
import { AutoGrowTextarea } from './AutoGrowTextarea';
import { MessageContentWithArtifacts } from '@/components/chat/MessageContentWithArtifacts';
import type { HubRemediation } from '@/services/hubApi';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  _key?: string;
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
  onHome?: () => void;
  onSendText?: (text: string) => void;
  isStreaming?: boolean;
  remediation?: HubRemediation[];
}

export function HubConversationView({
  messages, inputValue, setInputValue, onSend,
  showSlashMenu, slashQuery, onSlashSelect, onNewChat, onHome,
  onSendText, isStreaming, remediation,
}: HubConversationViewProps) {
  const { user } = useUser();
  const navigate = useNavigate();
  const scrollRef = useRef<HTMLDivElement>(null);

  const initials = (user?.full_name || user?.name || 'U')
    .split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  // Internal links inside assistant messages navigate via the SPA router
  // (no full-page reload); external links keep default browser behavior.
  const handleMessageAreaClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const anchor = (e.target as HTMLElement).closest('a');
    if (!anchor) return;
    const href = anchor.getAttribute('href') || '';
    if (!href || href.startsWith('http') || href.startsWith('mailto:') || anchor.target === '_blank') return;
    e.preventDefault();
    const path = href === '/huf' ? '/' : href.startsWith('/huf/') ? href.slice(4) : href;
    navigate(path);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !showSlashMenu) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Slim top bar — back to hub greeting without losing the conversation */}
      {onHome && (
        <div className="flex items-center px-3 py-2">
          <button
            onClick={onHome}
            title="Back to home"
            className="p-1.5 rounded-sm text-steel-soft hover:text-ink hover:bg-paper-deep transition-colors"
          >
            <Home className="w-4 h-4" />
          </button>
        </div>
      )}
      {/* Messages */}
      <div ref={scrollRef} onClick={handleMessageAreaClick} className="flex-1 min-h-0 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl w-full mx-auto space-y-4">
          {messages.map((msg, i) => (
            <motion.div
              key={msg._key ?? i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
            >
              <div className="flex-shrink-0">
                {msg.role === 'user' ? (
                  <div className="w-7 h-7 rounded-full bg-paper-deep border border-line flex items-center justify-center text-steel text-xs font-medium">
                    {initials}
                  </div>
                ) : (
                  <div className="w-7 h-7 rounded-full bg-panel border border-line flex items-center justify-center">
                    <Sparkles className="w-3.5 h-3.5 text-signal" />
                  </div>
                )}
              </div>
              <div className={`flex-1 min-w-0 ${msg.role === 'user' ? 'text-right' : ''}`}>
                {msg.role === 'assistant' && (
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="text-xs font-medium text-ink">Hub Orchestrator</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded-sm bg-paper-deep text-steel border border-line">System</span>
                  </div>
                )}
                {msg.content === '__NO_PROVIDER__' ? (
                  <div className="inline-block max-w-[85%] px-4 py-3 rounded-sm bg-warning border border-warning text-left">
                    <p className="text-sm font-medium text-warning mb-1">No AI Provider configured</p>
                    {remediation && remediation.length > 0 ? (
                      <ul className="text-xs text-warning mb-3 space-y-1">
                        {remediation.map((item) => (
                          <li key={item.code}>{item.message}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-warning mb-3">Add a provider and model to start using Hub Orchestrator.</p>
                    )}
                    <a href={remediation?.[0]?.action_route || '/models'} className="text-xs px-3 py-1.5 rounded-sm bg-signal text-white hover:bg-signal-ink transition-colors inline-block">
                      Add Provider →
                    </a>
                  </div>
                ) : msg.role === 'user' ? (
                  <div className="inline-block max-w-[85%] px-3 py-2 rounded-sm text-sm text-left bg-paper-deep border border-line text-ink">
                    {msg.content}
                  </div>
                ) : (
                  <div className="text-sm text-ink">
                    {(() => {
                      const { text, blocks } = splitAskUserBlocks(msg.content);
                      return (
                        <>
                          {text && (
                            <MessageContentWithArtifacts
                              content={text}
                              messageId={msg._key ?? `hub-msg-${i}`}
                            />
                          )}
                          {blocks.map((block, bi) => (
                            <HubAskUser
                              key={`${msg._key ?? i}-ask-${bi}`}
                              payload={block}
                              onSubmit={(answer) =>
                                onSendText?.(`Regarding "${block.question}": ${answer}`)
                              }
                            />
                          ))}
                        </>
                      );
                    })()}
                  </div>
                )}
              </div>
            </motion.div>
          ))}

          {/* Typing indicator */}
          {(messages.length > 0 && messages[messages.length - 1].role === 'user') || isStreaming ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3">
              <div className="w-7 h-7 rounded-full bg-panel border border-line flex items-center justify-center">
                <Sparkles className="w-3.5 h-3.5 text-signal" />
              </div>
              <div className="flex items-center gap-1 px-3 py-2 bg-paper-deep border border-line rounded-sm">
                {[0, 0.15, 0.3].map((delay, i) => (
                  <motion.div key={i} animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 0.6, repeat: Infinity, delay }} className="w-1.5 h-1.5 rounded-full bg-signal" />
                ))}
              </div>
            </motion.div>
          ) : null}
        </div>
      </div>

      {/* Input */}
      <div className="px-4 py-4 border-t border-line bg-panel">
        <div className="max-w-2xl mx-auto">
          <div className={`relative bg-panel border transition-all rounded-sm ${
            showSlashMenu ? 'border-signal' : 'border-line shadow-sm hover:border-steel-soft focus-within:border-signal'
          }`}>
            <AutoGrowTextarea
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Continue the conversation..."
              className="w-full px-4 py-3 pr-24 text-sm resize-none outline-none bg-transparent text-ink placeholder:text-steel-soft min-h-[52px]"
            />
            <div className="absolute right-2 bottom-2 flex items-center gap-1">
              <button onClick={onNewChat} className="p-1.5 rounded-sm text-steel-soft hover:text-signal-ink hover:bg-paper-deep transition-colors" title="New chat">
                <Plus className="w-4 h-4" />
              </button>
              <button onClick={onSend} disabled={!inputValue.trim()} className="p-1.5 rounded-sm bg-signal text-white disabled:bg-paper-deep disabled:text-steel-soft hover:bg-signal-ink transition-colors">
                <Send className="w-4 h-4" />
              </button>
            </div>
            <SlashCommandMenu isVisible={showSlashMenu} query={slashQuery} onSelect={onSlashSelect} placement="above" />
          </div>
        </div>
      </div>
    </div>
  );
}
