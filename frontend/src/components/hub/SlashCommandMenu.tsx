import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Workflow, Bot, Users, Database, DollarSign, BookOpen, Settings, ArrowRight } from 'lucide-react';

interface Command {
  id: string;
  label: string;
  description: string;
  icon: React.ElementType;
}

const COMMANDS: Command[] = [
  { id: '/flow', label: 'Flow', description: 'Create, edit, or manage workflows', icon: Workflow },
  { id: '/agent', label: 'Agent', description: 'Create, configure, or run agents', icon: Bot },
  { id: '/users', label: 'Users', description: 'Manage users and permissions', icon: Users },
  { id: '/runs', label: 'Executions', description: 'View and manage agent runs', icon: Database },
  { id: '/cost', label: 'Cost', description: 'View costs and optimize spending', icon: DollarSign },
  { id: '/knowledge', label: 'Knowledge', description: 'Index and search knowledge sources', icon: BookOpen },
  { id: '/settings', label: 'Settings', description: 'Configure providers and preferences', icon: Settings },
];

interface SlashCommandMenuProps {
  isVisible: boolean;
  query: string;
  onSelect: (command: string) => void;
}

export function SlashCommandMenu({ isVisible, query, onSelect }: SlashCommandMenuProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const filtered = query
    ? COMMANDS.filter(c => c.id.includes(query.toLowerCase()) || c.label.toLowerCase().includes(query.toLowerCase()))
    : COMMANDS;

  useEffect(() => { setSelectedIndex(0); }, [query]);

  useEffect(() => {
    if (!isVisible) return;
    const handle = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIndex(i => (i + 1) % filtered.length); }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedIndex(i => (i - 1 + filtered.length) % filtered.length); }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); if (filtered[selectedIndex]) onSelect(filtered[selectedIndex].id); }
    };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  }, [isVisible, filtered, selectedIndex, onSelect]);

  useEffect(() => {
    itemRefs.current[selectedIndex]?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  if (!isVisible || filtered.length === 0) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.1 }}
        className="absolute left-0 right-0 bottom-full mb-1 bg-white rounded-xl border border-violet-300 shadow-xl overflow-hidden z-50"
        style={{ maxHeight: 320 }}
      >
        <div className="overflow-y-auto py-1" style={{ maxHeight: 280 }}>
          {filtered.map((cmd, i) => (
            <button
              key={cmd.id}
              ref={el => { itemRefs.current[i] = el; }}
              onClick={() => onSelect(cmd.id)}
              onMouseEnter={() => setSelectedIndex(i)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors ${i === selectedIndex ? 'bg-violet-50' : 'hover:bg-slate-50'}`}
            >
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${i === selectedIndex ? 'bg-violet-100 text-violet-600' : 'bg-slate-100 text-slate-500'}`}>
                <cmd.icon className="w-4 h-4" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <code className={`text-sm font-mono font-medium ${i === selectedIndex ? 'text-violet-700' : 'text-slate-700'}`}>{cmd.id}</code>
                  <span className="text-xs text-slate-400">—</span>
                  <span className="text-sm text-slate-600">{cmd.label}</span>
                </div>
                <p className="text-xs text-slate-500 truncate">{cmd.description}</p>
              </div>
              {i === selectedIndex && <ArrowRight className="w-4 h-4 text-violet-500 flex-shrink-0" />}
            </button>
          ))}
        </div>
        <div className="px-3 py-2 border-t border-slate-100 bg-slate-50/50 flex items-center gap-4 text-[11px] text-slate-400">
          <span className="flex items-center gap-1"><kbd className="px-1.5 py-0.5 bg-white rounded border text-slate-500">↑↓</kbd> navigate</span>
          <span className="flex items-center gap-1"><kbd className="px-1.5 py-0.5 bg-white rounded border text-slate-500">↵</kbd> select</span>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
