import { useState } from 'react';
import {
  Check, X, ThumbsUp, ThumbsDown, Car, DollarSign, Calendar, User, Users,
  Settings, Bot, Workflow, Database, BookOpen, Cpu, Plus, Send, Sparkles,
  Home, LayoutDashboard, MessageSquare, CircleHelp,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';

export interface AskUserOption {
  id?: string;
  label: string;
  icon?: string;
  description?: string;
}

export interface AskUserPayload {
  question: string;
  kind: 'yes_no' | 'single_choice' | 'multi_choice' | 'input' | 'textarea';
  options?: AskUserOption[];
  allow_free_text?: boolean;
  suggested_answers?: string[];
  note?: string;
}

// Curated allowlist from the ask-user contract — unknown names fall back to CircleHelp
const ICONS: Record<string, LucideIcon> = {
  Check, X, ThumbsUp, ThumbsDown, Car, DollarSign, Calendar, User, Users,
  Settings, Bot, Workflow, Database, BookOpen, Cpu, Plus, Send, Sparkles,
  Home, LayoutDashboard, MessageSquare,
};

function iconFor(name?: string): LucideIcon {
  return (name && ICONS[name]) || CircleHelp;
}

const ASK_USER_RE = /```ask-user\s*\n?([\s\S]*?)```/g;

/** Pull fenced ```ask-user blocks out of assistant content. */
export function splitAskUserBlocks(content: string): { text: string; blocks: AskUserPayload[] } {
  const blocks: AskUserPayload[] = [];
  const text = content
    .replace(ASK_USER_RE, (match, json: string) => {
      try {
        const parsed = JSON.parse(json) as AskUserPayload;
        if (parsed && typeof parsed.question === 'string' && typeof parsed.kind === 'string') {
          blocks.push(parsed);
          return '';
        }
      } catch {
        // invalid JSON — leave the raw block visible in the text
      }
      return match;
    })
    // hide a still-streaming, unclosed block
    .replace(/```ask-user[\s\S]*$/, '')
    .trim();
  return { text, blocks };
}

interface HubAskUserProps {
  payload: AskUserPayload;
  onSubmit: (answer: string) => void;
}

export function HubAskUser({ payload, onSubmit }: HubAskUserProps) {
  const [answered, setAnswered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [text, setText] = useState('');
  const [showFreeText, setShowFreeText] = useState(false);

  const submit = (answer: string) => {
    const trimmed = answer.trim();
    if (!trimmed || answered) return;
    setAnswered(trimmed);
    onSubmit(trimmed);
  };

  const toggleOption = (label: string) => {
    if (payload.kind === 'multi_choice') {
      setSelected(prev =>
        prev.includes(label) ? prev.filter(l => l !== label) : [...prev, label]
      );
    } else {
      setSelected(prev => (prev.includes(label) ? [] : [label]));
    }
  };

  const isChoice = payload.kind === 'single_choice' || payload.kind === 'multi_choice';
  const isText = payload.kind === 'input' || payload.kind === 'textarea';

  return (
    <div className="mt-3 rounded-sm border border-line bg-panel p-3 max-w-md">
      <p className="text-sm font-medium text-ink">{payload.question}</p>
      {payload.note && <p className="mt-0.5 text-xs text-steel-soft">{payload.note}</p>}

      {answered !== null ? (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-steel">
          <Check className="w-3.5 h-3.5 text-signal" />
          <span className="opacity-80">{answered}</span>
        </div>
      ) : (
        <div className="mt-2.5 space-y-2">
          {payload.kind === 'yes_no' && (
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => submit('Yes')}
                className="h-auto gap-1.5 rounded-sm border-line bg-transparent px-3 py-1.5 text-xs font-normal text-ink hover:border-signal hover:bg-transparent hover:text-signal"
              >
                <Check className="w-3.5 h-3.5" /> Yes
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => submit('No')}
                className="h-auto gap-1.5 rounded-sm border-line bg-transparent px-3 py-1.5 text-xs font-normal text-ink hover:border-signal hover:bg-transparent hover:text-signal"
              >
                <X className="w-3.5 h-3.5" /> No
              </Button>
            </div>
          )}

          {isChoice && (
            <>
              <div className="grid gap-1.5">
                {(payload.options ?? []).map(opt => {
                  const Icon = iconFor(opt.icon);
                  const active = selected.includes(opt.label);
                  return (
                    <Button
                      key={opt.id ?? opt.label}
                      type="button"
                      variant="ghost"
                      onClick={() => toggleOption(opt.label)}
                      className={`flex h-auto w-full items-start justify-start gap-2 rounded-sm border p-2 text-left font-normal transition-colors hover:bg-transparent ${
                        active
                          ? 'border-signal bg-paper-deep'
                          : 'border-line hover:border-steel-soft'
                      }`}
                    >
                      <Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${active ? 'text-signal' : 'text-steel-soft'}`} />
                      <span className="min-w-0">
                        <span className={`block text-xs font-medium ${active ? 'text-ink' : 'text-steel'}`}>{opt.label}</span>
                        {opt.description && <span className="block text-[11px] text-steel-soft">{opt.description}</span>}
                      </span>
                    </Button>
                  );
                })}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => submit(selected.join(', '))}
                  disabled={selected.length === 0}
                  className="px-3 py-1.5 rounded-sm bg-signal text-white text-xs disabled:bg-paper-deep disabled:text-steel-soft hover:bg-signal-ink transition-colors"
                >
                  Submit
                </button>
                {payload.allow_free_text && !showFreeText && (
                  <button
                    onClick={() => setShowFreeText(true)}
                    className="text-xs text-steel-soft hover:text-signal transition-colors"
                  >
                    Something else…
                  </button>
                )}
              </div>
            </>
          )}

          {(isText || (isChoice && payload.allow_free_text && showFreeText)) && (
            <div className="space-y-1.5">
              {payload.kind === 'textarea' ? (
                <textarea
                  value={text}
                  onChange={e => setText(e.target.value)}
                  rows={3}
                  placeholder="Type your answer..."
                  className="w-full px-2.5 py-1.5 rounded-sm border border-line bg-paper text-xs text-ink placeholder:text-steel-soft resize-none outline-none focus:border-signal"
                />
              ) : (
                <input
                  type="text"
                  value={text}
                  onChange={e => setText(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') { e.preventDefault(); submit(text); }
                  }}
                  placeholder="Type your answer..."
                  className="w-full px-2.5 py-1.5 rounded-sm border border-line bg-paper text-xs text-ink placeholder:text-steel-soft outline-none focus:border-signal"
                />
              )}
              {isText && (payload.suggested_answers?.length ?? 0) > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {payload.suggested_answers!.map(s => (
                    <button
                      key={s}
                      onClick={() => setText(s)}
                      className="px-2 py-1 rounded-sm border border-line text-[11px] text-steel hover:border-signal hover:text-signal transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
              <button
                onClick={() => submit(text)}
                disabled={!text.trim()}
                className="px-3 py-1.5 rounded-sm bg-signal text-white text-xs disabled:bg-paper-deep disabled:text-steel-soft hover:bg-signal-ink transition-colors"
              >
                Submit
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
