import { Clock, Play, Save, MessageSquare, MoreVertical, Copy, FileText, Trash2 } from 'lucide-react';
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
import type { AIProvider, AIModel } from '@/types/agent.types';
import type { AgentFormValues } from './types';

interface AgentHeaderProps {
  form: UseFormReturn<AgentFormValues>;
  watchDisabled: boolean;
  providers: AIProvider[];
  models: AIModel[];
  activeTriggerCount: number;
  isNew: boolean;
  showSaveButton: boolean;
  saving: boolean;
  onSave: () => void;
  onRunTest: () => void;
  onDuplicate: () => void;
  onViewLogs: () => void;
  onDelete: () => void;
  agentId?: string;
}

export function AgentHeader({
  form,
  watchDisabled,
  providers,
  models,
  activeTriggerCount,
  isNew,
  showSaveButton,
  saving,
  onSave,
  onRunTest,
  onDuplicate,
  onViewLogs,
  onDelete,
  agentId,
}: AgentHeaderProps) {
  const watchProvider = form.watch('provider');
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
          <Input
            value={form.watch('agent_name')}
            onChange={(e) => form.setValue('agent_name', e.target.value, { shouldDirty: true })}
            className="text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-md"
            placeholder="Agent Name"
          />
          <Badge variant={watchDisabled ? 'secondary' : 'default'}>
            {watchDisabled ? 'Disabled' : 'Active'}
          </Badge>
          <Badge variant="outline">
            {providers.find(p => p.name === watchProvider)?.provider_name || watchProvider || 'Provider'}
          </Badge>
          <Badge variant="outline">
            {models.find(m => m.name === watchModel)?.model_name || watchModel || 'Model'}
          </Badge>
        </div>
        {activeTriggerCount > 0 && (
          <div className="text-sm text-muted-foreground flex items-center gap-2">
            <Clock className="w-4 h-4" />
            {activeTriggerCount} active {activeTriggerCount === 1 ? 'trigger' : 'triggers'}
          </div>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="icon" onClick={onRunTest} type="button">
          <Play className="w-4 h-4" />
        </Button>
        <Button variant="outline" size="sm" type="button" onClick={handleOpenChat}>
          <MessageSquare className="w-4 h-4 mr-2" />
          Chat
        </Button>
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
                  onCheckedChange={(checked) => form.setValue('disabled', checked)}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
            </div>
            {!isNew && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={onDuplicate}>
                  <Copy className="w-4 h-4 mr-2" />
                  Duplicate
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onViewLogs}>
                  <FileText className="w-4 h-4 mr-2" />
                  View Logs
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onDelete} className="text-destructive">
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
