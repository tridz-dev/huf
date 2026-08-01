import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Save } from 'lucide-react';
import { ConsoleTemplatePicker } from './ConsoleTemplatePicker';
import type { AgentPromptDoc } from '@/services/agentPromptApi';

export type ConsoleMode = 'playground' | 'compare' | 'templates';

interface ConsoleHeaderProps {
  mode: ConsoleMode;
  onModeChange: (mode: ConsoleMode) => void;
  onSaveTemplate: () => void;
  onLoadTemplate: (prompt: AgentPromptDoc) => void;
  canSave: boolean;
}

export function ConsoleHeader({
  mode,
  onModeChange,
  onSaveTemplate,
  onLoadTemplate,
  canSave,
}: ConsoleHeaderProps) {
  return (
    <header className="flex shrink-0 flex-col border-b border-line bg-panel">
      <div className="flex h-14 items-center justify-between px-4">
        <h1 className="text-xl font-semibold">Console</h1>
        <div className="flex items-center gap-2">
          <ConsoleTemplatePicker onLoadTemplate={onLoadTemplate} />
          <Button
            size="sm"
            variant="secondary"
            onClick={onSaveTemplate}
            disabled={!canSave}
            className="gap-1.5"
          >
            <Save className="h-4 w-4" />
            Save as template
          </Button>
        </div>
      </div>

      <Tabs value={mode} onValueChange={(value) => onModeChange(value as ConsoleMode)}>
        <TabsList variant="panel" className="px-4">
          <TabsTrigger value="playground" className="uppercase tracking-wide">
            Playground
          </TabsTrigger>
          <TabsTrigger value="compare" className="uppercase tracking-wide">
            Compare
          </TabsTrigger>
          <TabsTrigger value="templates" className="uppercase tracking-wide">
            Templates
          </TabsTrigger>
        </TabsList>
      </Tabs>
    </header>
  );
}
