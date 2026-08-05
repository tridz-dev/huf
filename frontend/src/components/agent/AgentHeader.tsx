import { Clock, Play, Save, MessageSquare, MoreVertical, FileText, Lock, Copy, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { useNavigate } from 'react-router-dom';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { UseFormReturn } from 'react-hook-form';
import type { AIModel } from '@/types/agent.types';
import type { AgentFormValues } from './types';
import { formatTimeAgo } from '@/utils/time';
import { InlineEditName } from '@/components/common/InlineEditName';

interface AgentHeaderProps {
  form: UseFormReturn<AgentFormValues>;
  watchDisabled: boolean;
  models: AIModel[];
  activeTriggerCount: number;
  isNew: boolean;
  /** True when the agent is a protected system agent (is_system=1). */
  isSystem?: boolean;
  /** True when protected fields must be read-only (system agent + non-admin). */
  locked?: boolean;
  showSaveButton: boolean;
  saving: boolean;
  runningTest?: boolean;
  onSave: () => void;
  onRunTest: () => void;
  onDuplicate: () => void;
  onViewLogs: () => void;
  onDelete: () => void;
  duplicating?: boolean;
  agentId?: string;
  allowChat: boolean;
  lastRun?: string | null;
  totalRun?: number | null;
}

export function AgentHeader({
  form,
  watchDisabled,
  models,
  activeTriggerCount,
  isNew,
  isSystem = false,
  locked = false,
  showSaveButton,
  saving,
  runningTest = false,
  onSave,
  onRunTest,
  onDuplicate,
  onViewLogs,
  onDelete,
  duplicating = false,
  agentId,
  allowChat,
  lastRun,
  totalRun,
}: AgentHeaderProps) {
  const watchModel = form.watch('model');
  const navigate = useNavigate();

  const handleOpenChat = () => {
    if (agentId) {
      const params = new URLSearchParams({ agent: agentId });
      navigate(`/chat?${params.toString()}`);
      return;
    }
    navigate('/chat');
  };

  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div className="flex-1 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          {isNew ? (
            <Input
              value={form.watch('agent_name')}
              onChange={(e) => form.setValue('agent_name', e.target.value, { shouldDirty: true })}
              className="text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-md"
              placeholder="Agent Name"
            />
          ) : (
            <InlineEditName
              value={form.watch('agent_name')}
              onChange={(value) => form.setValue('agent_name', value, { shouldDirty: true })}
              placeholder="Agent Name"
            />
          )}
          <Badge variant={watchDisabled ? 'pill-neutral' : 'pill-success'}>
            <span className={`w-1.5 h-1.5 rounded-full mr-1 ${watchDisabled ? 'bg-steel-soft' : 'bg-good'}`} />
            {watchDisabled ? 'Disabled' : 'Active'}
          </Badge>
          {isSystem && (
            <Badge variant="pill-neutral" className="gap-1">
              <Lock className="w-3 h-3" />
              System
            </Badge>
          )}
          <Badge variant="chip">
            {models.find(m => m.name === watchModel)?.model_name || watchModel || 'Model'}
          </Badge>
          {activeTriggerCount > 0 && (
            <span className="text-xs text-steel-soft flex items-center gap-1">
              <Clock className="w-3 h-3 shrink-0" />
              {activeTriggerCount} active {activeTriggerCount === 1 ? 'trigger' : 'triggers'}
            </span>
          )}
          {!isNew && (lastRun !== undefined || totalRun !== undefined) && (
            <span className="text-xs text-steel-soft ml-1">
              Last run {lastRun ? formatTimeAgo(lastRun) : 'never'} &middot; {totalRun ?? 0} runs
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {!isNew && (<Button 
          variant="outline" 
          size="icon-sm" 
          onClick={onRunTest} 
          type="button"
          disabled={runningTest || isNew}
          title={isNew ? 'Save agent first to run test' : runningTest ? 'Running...' : 'Run test'}
        >
          <Play className="w-4 h-4" />
        </Button>)}
        {(!isNew && allowChat) && (<Button variant="outline" size="sm" type="button" onClick={handleOpenChat}>
          <MessageSquare className="w-4 h-4 mr-2" />
          Chat
        </Button>)}
        {showSaveButton && (
          <Button size="sm" onClick={onSave} disabled={saving}>
            <Save className="w-4 h-4 mr-2" />
            {saving ? (isNew ? 'Creating...' : 'Saving...') : (isNew ? 'Create' : 'Save')}
          </Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              <MoreVertical className="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <div className="px-2 py-1.5">
              <div className="flex items-center justify-between">
                <span className="text-sm">Disable</span>
                <Switch
                  checked={watchDisabled}
                  disabled={locked}
                  onCheckedChange={(checked) => form.setValue('disabled', checked)}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
            </div>
            {!isNew && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onDuplicate} disabled={duplicating || locked}>
                  <Copy className="w-4 h-4 mr-2" />
                  {duplicating ? 'Duplicating...' : 'Duplicate'}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onViewLogs}>
                  <FileText className="w-4 h-4 mr-2" />
                  View Logs
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onDelete} disabled={locked} className="text-destructive">
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
