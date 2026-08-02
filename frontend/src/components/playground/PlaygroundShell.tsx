import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, Loader2, Play } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { WorkSurfaceFrame, type WorkSurfaceTab } from '@/layouts/WorkSurfaceFrame';
import type { PlaygroundMode } from './types';

interface PlaygroundShellProps {
  mode: PlaygroundMode;
  onModeChange: (mode: PlaygroundMode) => void;
  onRun: () => void;
  running: boolean;
  canSaveTemplate: boolean;
  onLoadTemplate: () => void;
  onSaveTemplate: () => void;
  children: ReactNode;
}

const tabs: WorkSurfaceTab[] = [
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
  children,
}: PlaygroundShellProps) {
  const actions = (
    <>
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
    </>
  );

  return (
    <WorkSurfaceFrame
      title="Playground"
      actions={actions}
      tabs={{
        value: mode,
        onValueChange: (value) => onModeChange(value as PlaygroundMode),
        items: tabs,
      }}
    >
      {children}
    </WorkSurfaceFrame>
  );
}
