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
import { Button } from '@/components/ui/button';
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
  { value: 'playground', label: 'Single' },
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
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5">
            Templates
            <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.8} />
          </Button>
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

      <Button type="button" onClick={onRun} disabled={running} className="gap-2">
        {running ? 'Running' : mode === 'compare' ? 'Run both' : 'Run'}
        {running ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <Play className="h-3 w-3 fill-current" />
        )}
      </Button>
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
