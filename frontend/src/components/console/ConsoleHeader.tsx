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
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-panel px-4">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-semibold">Console</h1>
        <Tabs value={mode} onValueChange={(value) => onModeChange(value as ConsoleMode)}>
          <TabsList className="h-8">
            <TabsTrigger value="playground" className="text-xs">
              Playground
            </TabsTrigger>
            <TabsTrigger value="compare" className="text-xs">
              Compare
            </TabsTrigger>
            <TabsTrigger value="templates" className="text-xs">
              Templates
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

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
    </header>
  );
}
