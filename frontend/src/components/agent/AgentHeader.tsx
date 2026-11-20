import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Copy, FileText, Lock, MessageSquare, MoreVertical, Save, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { formatTimeAgo } from '@/utils/time';

interface AgentHeaderProps {
  title: string;
  disabled: boolean;
  /** Model label chip; omitted for voice-only agents. */
  modelLabel?: string;
  /** True when the agent is a protected system agent (is_system=1). */
  isSystem?: boolean;
  /** True when protected fields must be read-only (system agent + non-admin). */
  locked?: boolean;
  /** AutosaveStatus element. */
  autosave: ReactNode;
  showSave: boolean;
  saving: boolean;
  onSave: () => void;
  /** Publish (enable) or disable the agent. */
  onTogglePublish: () => void;
  onDuplicate: () => void;
  onViewLogs: () => void;
  onDelete: () => void;
  duplicating?: boolean;
  agentId: string;
  allowChat: boolean;
  lastRun?: string | null;
  totalRun?: number | null;
}

export function AgentHeader({
  title, disabled, modelLabel, isSystem = false, locked = false, autosave, showSave, saving, onSave, onTogglePublish,
  onDuplicate, onViewLogs, onDelete, duplicating = false, agentId, allowChat, lastRun, totalRun,
}: AgentHeaderProps) {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="truncate text-title font-semibold text-ink">{title}</h1>
          <Badge variant={disabled ? 'pill-neutral' : 'pill-success'}>
            <span className={`mr-1 h-1.5 w-1.5 rounded-full ${disabled ? 'bg-steel-soft' : 'bg-good'}`} />
            {disabled ? 'Disabled' : 'Active'}
          </Badge>
          {isSystem && <Badge variant="pill-neutral" className="gap-1"><Lock className="h-3 w-3" />System</Badge>}
          {modelLabel && <Badge variant="chip">{modelLabel}</Badge>}
          {autosave}
        </div>
        {(lastRun !== undefined || totalRun !== undefined) && (
          <p className="text-xs text-steel-soft">Last run {lastRun ? formatTimeAgo(lastRun) : 'never'} &middot; {totalRun ?? 0} runs</p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {allowChat && (
          <Button variant="outline" size="sm" type="button" onClick={() => navigate(`/chat?${new URLSearchParams({ agent: agentId }).toString()}`)}>
            <MessageSquare className="mr-2 h-4 w-4" />Chat
          </Button>
        )}
        <Button variant="outline" size="sm" type="button" onClick={onDuplicate} disabled={duplicating || locked}>
          <Copy className="mr-2 h-4 w-4" />{duplicating ? 'Duplicating...' : 'Duplicate'}
        </Button>
        {showSave && (
          <Button variant="outline" size="sm" type="button" onClick={onSave} disabled={saving}>
            <Save className="mr-2 h-4 w-4" />{saving ? 'Saving...' : 'Save now'}
          </Button>
        )}
        <Button size="sm" type="button" variant={disabled ? 'default' : 'outline'} onClick={onTogglePublish} disabled={locked}>
          {disabled ? 'Publish' : 'Disable'}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" aria-label="More actions"><MoreVertical className="h-4 w-4" /></Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onViewLogs}><FileText className="mr-2 h-4 w-4" />View logs</DropdownMenuItem>
            <DropdownMenuItem onClick={onDelete} disabled={locked} className="text-destructive"><Trash2 className="mr-2 h-4 w-4" />Delete</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
