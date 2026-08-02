import { Link } from 'react-router-dom';
import { ChevronDown, Loader2, Play } from 'lucide-react';
import { SidebarTrigger } from '@/components/ui/sidebar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import type { PlaygroundMode } from './types';

interface PlaygroundShellProps {
  mode: PlaygroundMode;
  onModeChange: (mode: PlaygroundMode) => void;
  onRun: () => void;
  running: boolean;
  canSaveTemplate: boolean;
  onLoadTemplate: () => void;
  onSaveTemplate: () => void;
}

const tabs: { value: PlaygroundMode; label: string }[] = [
  { value: 'playground', label: 'Playground' },
  { value: 'compare', label: 'Compare' },
];

export function PlaygroundShell({
  mode,
  onModeChange,
  onRun,
  running,
  canSaveTemplate,
  onLoadTemplate,
  onSaveTemplate,
}: PlaygroundShellProps) {
  return (
    <>
      {/* Topbar */}
      <header className="flex items-center justify-between border-b border-line bg-panel px-5 py-3.5">
        <div className="flex items-center gap-3.5">
          <SidebarTrigger className="-ml-1 text-steel hover:bg-transparent hover:text-ink" />
          <h1 className="font-display text-xl font-bold uppercase leading-none">Playground</h1>
        </div>

        <div className="flex items-center gap-2.5">
          <DropdownMenu>
            <DropdownMenuTrigger className="flex items-center gap-1.5 rounded border border-line px-3 py-[7px] text-[13px] text-steel outline-none transition-colors hover:border-ink/40 hover:text-ink data-[state=open]:border-ink/40 data-[state=open]:text-ink">
              Templates
              <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.8} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuItem onSelect={onLoadTemplate}>Load template…</DropdownMenuItem>
              <DropdownMenuItem onSelect={onSaveTemplate} disabled={!canSaveTemplate}>
                Save current as template
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link to="/prompts">Manage templates</Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <button
            type="button"
            onClick={onRun}
            disabled={running}
            className="flex items-center gap-2 rounded bg-ink px-4 py-2 font-display text-[13px] font-bold uppercase tracking-[.06em] text-paper transition-colors hover:bg-signal disabled:cursor-not-allowed disabled:opacity-50"
          >
            {running ? 'Running' : mode === 'compare' ? 'Run both' : 'Run'}
            {running ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Play className="h-3 w-3 fill-current" />
            )}
          </button>
        </div>
      </header>

      {/* Mode tabs — sentence-case Plex Sans on a shared baseline, signal underline */}
      <div className="flex border-b border-line bg-paper px-5">
        {tabs.map((tab) => (
          <button
            key={tab.value}
            type="button"
            onClick={() => onModeChange(tab.value)}
            className={cn(
              '-mb-px mr-6 border-b-2 px-1 py-3 text-[13px] transition-colors',
              mode === tab.value
                ? 'border-signal text-ink'
                : 'border-transparent text-steel hover:text-ink',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </>
  );
}
