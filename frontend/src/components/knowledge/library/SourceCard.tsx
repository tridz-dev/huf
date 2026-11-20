import { MoreVertical, Pause, Pencil, Play, Search, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { BaseCard } from '@/components/dashboard/cards/BaseCard';
import {
  HEALTH_BADGE,
  HEALTH_HINT,
  HEALTH_LABEL,
  computeHealth,
  type InputCounts,
} from '@/components/agent/knowledge/sourceHealth';
import { formatTimeAgo } from '@/utils/time';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';

interface SourceCardProps {
  source: KnowledgeSourceDoc;
  counts: InputCounts;
  agentCount: number;
  onOpen: () => void;
  onTest: () => void;
  onAddFiles: () => void;
  onRename: () => void;
  onToggleDisabled: () => void;
  onDelete: () => void;
}

export function SourceCard({ source, counts, agentCount, onOpen, onTest, onAddFiles, onRename, onToggleDisabled, onDelete }: SourceCardProps) {
  const health = computeHealth(source, counts);
  const stop = (fn: () => void) => (e: React.MouseEvent) => {
    e.stopPropagation();
    fn();
  };
  const docs = `${counts.total.toLocaleString()} ${counts.total === 1 ? 'document' : 'documents'}`;
  const hint = health === 'attention' ? `${counts.failed} ${counts.failed === 1 ? 'document' : 'documents'} could not be read.` : HEALTH_HINT[health];
  return (
    <BaseCard onClick={onOpen} className="flex flex-col p-5 gap-3">
      <div className="flex items-start justify-between gap-2">
        <h3 className="min-w-0 truncate text-body-text font-semibold" title={source.source_name || source.name}>
          {source.source_name || source.name}
        </h3>
        <Badge variant={HEALTH_BADGE[health]} size="sm" title={hint}>{HEALTH_LABEL[health]}</Badge>
      </div>
      <div className="space-y-0.5 text-sm text-steel">
        <p>{docs} · Updated {formatTimeAgo(source.modified || source.creation)}</p>
        {agentCount > 0 && <p>Used by {agentCount} {agentCount === 1 ? 'agent' : 'agents'}</p>}
        <p className="text-xs">{hint}</p>
      </div>
      <div className="mt-auto flex items-center gap-2 pt-1">
        <Button size="sm" variant="outline" onClick={stop(onAddFiles)}>Add content</Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="ml-auto" title="More actions" onClick={(e) => e.stopPropagation()}>
              <MoreVertical className="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
            <DropdownMenuItem onClick={stop(onTest)}><Search className="w-4 h-4 mr-2" />Test</DropdownMenuItem>
            <DropdownMenuItem onClick={stop(onRename)}><Pencil className="w-4 h-4 mr-2" />Rename</DropdownMenuItem>
            <DropdownMenuItem onClick={stop(onToggleDisabled)}>
              {source.disabled ? <Play className="w-4 h-4 mr-2" /> : <Pause className="w-4 h-4 mr-2" />}
              {source.disabled ? 'Turn on' : 'Turn off'}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={stop(onDelete)} className="text-destructive focus:text-destructive">
              <Trash2 className="w-4 h-4 mr-2" />Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </BaseCard>
  );
}
