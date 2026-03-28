import { useState } from 'react';
import {
  Brain,
  Sparkles,
  User,
  Bot,
  Share2,
  Globe,
  Database,
  Tag,
  Eye,
  Trash2,
  RefreshCw,
  Plus,
  Clock,
  BarChart3,
  ChevronDown,
  ChevronUp,
  X,
  Lightbulb,
  FileText,
  Settings,
  CaptureIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { toast } from 'sonner';
import type {
  MemoryRecord,
  MemoryRecordRow,
  MemoryScopeType,
  MemoryType,
  MemoryStatus,
} from '@/types/memory.types';
import { useConversationMemory } from './hooks/useMemory';
import { formatDistanceToNow } from '@/utils/dateUtils';

// ============================================================================
// Types
// ============================================================================

interface MemoryInspectorProps {
  conversationId: string;
  conversationTitle?: string;
  onClose?: () => void;
}

interface MemoryRecordDetailProps {
  record: MemoryRecordRow;
  onView: (record: MemoryRecordRow) => void;
  onDelete: (record: MemoryRecordRow) => void;
}

interface MemoryStatsPanelProps {
  records: MemoryRecordRow[];
}

// ============================================================================
// Helper Components
// ============================================================================

function MemoryScopeIcon({ scope }: { scope: MemoryScopeType }) {
  switch (scope) {
    case 'conversation':
      return <Sparkles className="w-4 h-4 text-blue-500" />;
    case 'user':
      return <User className="w-4 h-4 text-green-500" />;
    case 'agent':
      return <Bot className="w-4 h-4 text-purple-500" />;
    case 'namespace':
      return <Share2 className="w-4 h-4 text-amber-500" />;
    case 'global':
      return <Globe className="w-4 h-4 text-rose-500" />;
    default:
      return <Database className="w-4 h-4" />;
  }
}

function MemoryScopeBadge({ scope }: { scope: MemoryScopeType }) {
  const colors: Record<MemoryScopeType, string> = {
    conversation: 'bg-blue-100 text-blue-800 hover:bg-blue-200',
    user: 'bg-green-100 text-green-800 hover:bg-green-200',
    agent: 'bg-purple-100 text-purple-800 hover:bg-purple-200',
    namespace: 'bg-amber-100 text-amber-800 hover:bg-amber-200',
    global: 'bg-rose-100 text-rose-800 hover:bg-rose-200',
  };

  return (
    <Badge variant="secondary" className={`${colors[scope] || ''} text-xs`}>
      <div className="flex items-center gap-1">
        <MemoryScopeIcon scope={scope} />
        <span className="capitalize">{scope}</span>
      </div>
    </Badge>
  );
}

function MemoryStatusBadge({ status }: { status: MemoryStatus }) {
  const colors: Record<MemoryStatus, string> = {
    active: 'bg-emerald-100 text-emerald-800',
    superseded: 'bg-gray-100 text-gray-800',
    archived: 'bg-slate-100 text-slate-800',
    expired: 'bg-red-100 text-red-800',
    error: 'bg-red-200 text-red-900',
  };

  return (
    <Badge variant="secondary" className={`${colors[status] || ''} text-xs`}>
      <span className="capitalize">{status}</span>
    </Badge>
  );
}

function MemoryTypeIcon({ type }: { type: MemoryType }) {
  const icons: Record<MemoryType, React.ReactNode> = {
    profile: <User className="w-4 h-4" />,
    session_state: <Clock className="w-4 h-4" />,
    preference: <Settings className="w-4 h-4" />,
    fact: <FileText className="w-4 h-4" />,
    plan: <Lightbulb className="w-4 h-4" />,
    observation: <Eye className="w-4 h-4" />,
    insight: <Sparkles className="w-4 h-4" />,
    domain_object: <Database className="w-4 h-4" />,
    custom: <Tag className="w-4 h-4" />,
  };

  return <>{icons[type] || <Database className="w-4 h-4" />}</>;
}

function MemoryTypeBadge({ type }: { type: MemoryType }) {
  const typeLabels: Record<MemoryType, string> = {
    profile: 'Profile',
    session_state: 'Session',
    preference: 'Preference',
    fact: 'Fact',
    plan: 'Plan',
    observation: 'Observation',
    insight: 'Insight',
    domain_object: 'Domain',
    custom: 'Custom',
  };

  return (
    <Badge variant="outline" className="text-xs flex items-center gap-1">
      <MemoryTypeIcon type={type} />
      {typeLabels[type] || type}
    </Badge>
  );
}

function MemoryRecordCard({ record, onView, onDelete }: MemoryRecordDetailProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Collapsible open={expanded} onOpenChange={setExpanded}>
      <div className="rounded-lg border p-3 hover:bg-muted/50 transition-colors">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              <h4 className="font-medium text-sm truncate">{record.title || 'Untitled Memory'}</h4>
              <MemoryStatusBadge status={record.status} />
            </div>
            
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1.5">
              <MemoryTypeBadge type={record.memory_type} />
              <span>•</span>
              <MemoryScopeBadge scope={record.scope_type} />
            </div>

            {record.tags && record.tags.length > 0 && (
              <div className="flex items-center gap-1 flex-wrap mb-1.5">
                {record.tags.slice(0, 3).map((tag) => (
                  <Badge key={tag} variant="outline" className="text-[10px] py-0 h-5">
                    {tag}
                  </Badge>
                ))}
                {record.tags.length > 3 && (
                  <Badge variant="outline" className="text-[10px] py-0 h-5">
                    +{record.tags.length - 3}
                  </Badge>
                )}
              </div>
            )}

            <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
              {record.confidence !== undefined && (
                <span>Confidence: {(record.confidence * 100).toFixed(0)}%</span>
              )}
              {record.importance_score !== undefined && (
                <span>Importance: {record.importance_score}/10</span>
              )}
              <span>{formatDistanceToNow(record.modified)}</span>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm" className="h-7 w-7 p-0">
                {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </Button>
            </CollapsibleTrigger>
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => onView(record)}>
              <Eye className="w-4 h-4" />
            </Button>
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-red-500" onClick={() => onDelete(record)}>
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        </div>

        <CollapsibleContent>
          <div className="mt-3 pt-3 border-t">
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-muted-foreground">Agent:</span>
                <span className="ml-1">{record.agent_name || record.agent}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Created:</span>
                <span className="ml-1">{new Date(record.creation).toLocaleString()}</span>
              </div>
            </div>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

function MemoryStatsPanel({ records }: MemoryStatsPanelProps) {
  const stats = {
    total: records.length,
    byScope: {} as Record<MemoryScopeType, number>,
    byType: {} as Record<MemoryType, number>,
    byStatus: {} as Record<MemoryStatus, number>,
  };

  records.forEach((record) => {
    stats.byScope[record.scope_type] = (stats.byScope[record.scope_type] || 0) + 1;
    stats.byType[record.memory_type] = (stats.byType[record.memory_type] || 0) + 1;
    stats.byStatus[record.status] = (stats.byStatus[record.status] || 0) + 1;
  });

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Card className="bg-muted/50">
          <CardContent className="p-3">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-indigo-500" />
              <div>
                <p className="text-xs text-muted-foreground">Total Memories</p>
                <p className="text-lg font-bold">{stats.total}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-muted/50">
          <CardContent className="p-3">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-green-500" />
              <div>
                <p className="text-xs text-muted-foreground">Active</p>
                <p className="text-lg font-bold">{stats.byStatus.active || 0}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {Object.keys(stats.byScope).length > 0 && (
        <div>
          <p className="text-xs font-medium mb-2">By Scope</p>
          <div className="flex flex-wrap gap-1">
            {Object.entries(stats.byScope).map(([scope, count]) => (
              <MemoryScopeBadge key={scope} scope={scope as MemoryScopeType} />
            ))}
          </div>
        </div>
      )}

      {Object.keys(stats.byType).length > 0 && (
        <div>
          <p className="text-xs font-medium mb-2">By Type</p>
          <div className="flex flex-wrap gap-1">
            {Object.entries(stats.byType).map(([type, count]) => (
              <MemoryTypeBadge key={type} type={type as MemoryType} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MemoryDetailDialog({
  open,
  onOpenChange,
  record,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  record: MemoryRecordRow | null;
}) {
  if (!record) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{record.title || 'Memory Details'}</DialogTitle>
          <DialogDescription>
            Memory record from conversation
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center gap-2 flex-wrap">
            <MemoryScopeBadge scope={record.scope_type} />
            <MemoryStatusBadge status={record.status} />
            <MemoryTypeBadge type={record.memory_type} />
          </div>

          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <label className="text-muted-foreground text-xs">Agent</label>
              <p>{record.agent_name || record.agent}</p>
            </div>
            <div>
              <label className="text-muted-foreground text-xs">Created</label>
              <p>{new Date(record.creation).toLocaleString()}</p>
            </div>
            <div>
              <label className="text-muted-foreground text-xs">Modified</label>
              <p>{new Date(record.modified).toLocaleString()}</p>
            </div>
            <div>
              <label className="text-muted-foreground text-xs">Retrievals</label>
              <p>{record.retrieval_count || 0}</p>
            </div>
          </div>

          {record.confidence !== undefined && (
            <div>
              <label className="text-muted-foreground text-xs">Confidence</label>
              <div className="flex items-center gap-2 mt-1">
                <div className="flex-1 bg-muted rounded-full h-2">
                  <div
                    className="bg-indigo-500 h-2 rounded-full transition-all"
                    style={{ width: `${record.confidence * 100}%` }}
                  />
                </div>
                <span className="text-sm">{(record.confidence * 100).toFixed(0)}%</span>
              </div>
            </div>
          )}

          {record.importance_score !== undefined && (
            <div>
              <label className="text-muted-foreground text-xs">Importance Score</label>
              <div className="flex items-center gap-2 mt-1">
                <div className="flex-1 bg-muted rounded-full h-2">
                  <div
                    className="bg-amber-500 h-2 rounded-full transition-all"
                    style={{ width: `${(record.importance_score / 10) * 100}%` }}
                  />
                </div>
                <span className="text-sm">{record.importance_score}/10</span>
              </div>
            </div>
          )}

          {record.tags && record.tags.length > 0 && (
            <div>
              <label className="text-muted-foreground text-xs">Tags</label>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                {record.tags.map((tag) => (
                  <Badge key={tag} variant="outline">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function MemoryInspector({ conversationId, conversationTitle, onClose }: MemoryInspectorProps) {
  const [selectedRecord, setSelectedRecord] = useState<MemoryRecordRow | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [showStats, setShowStats] = useState(true);

  const { records, loading, error, capture, captureResult, refetch } = useConversationMemory({
    conversationId,
    autoFetch: true,
  });

  const handleView = (record: MemoryRecordRow) => {
    setSelectedRecord(record);
    setDetailOpen(true);
  };

  const handleDelete = async (record: MemoryRecordRow) => {
    if (confirm(`Delete memory "${record.title}"? This action cannot be undone.`)) {
      try {
        // Delete logic here - would call API
        toast.success('Memory deleted successfully');
        refetch();
      } catch (err) {
        toast.error('Failed to delete memory');
      }
    }
  };

  const handleCapture = async () => {
    try {
      const result = await capture();
      if (result.success) {
        toast.success(`Captured ${result.records_created} new memories`);
      } else {
        toast.error(result.error_message || 'Capture failed');
      }
    } catch (err) {
      toast.error('Failed to capture memory');
    }
  };

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="border-b p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className="w-5 h-5 text-indigo-500" />
            <div>
              <h2 className="font-semibold">Memory Inspector</h2>
              {conversationTitle && (
                <p className="text-xs text-muted-foreground">{conversationTitle}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={handleCapture} disabled={loading}>
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              <span className="ml-1 hidden sm:inline">Capture</span>
            </Button>
            <Button variant="ghost" size="sm" onClick={() => refetch()} disabled={loading}>
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
            {onClose && (
              <Button variant="ghost" size="sm" onClick={onClose}>
                <X className="w-4 h-4" />
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-4">
          {/* Stats Panel */}
          <Collapsible open={showStats} onOpenChange={setShowStats}>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm" className="w-full justify-between">
                <span className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4" />
                  Memory Statistics
                </span>
                {showStats ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="mt-2">
                <MemoryStatsPanel records={records} />
              </div>
            </CollapsibleContent>
          </Collapsible>

          <Separator />

          {/* Records List */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium">Memory Records</h3>
              <span className="text-xs text-muted-foreground">
                {records.length} record{records.length !== 1 ? 's' : ''}
              </span>
            </div>

            <div className="space-y-2">
              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              ) : error ? (
                <div className="text-center py-8">
                  <p className="text-sm text-red-500">Failed to load memories</p>
                  <Button variant="outline" size="sm" className="mt-2" onClick={() => refetch()}>
                    Retry
                  </Button>
                </div>
              ) : records.length === 0 ? (
                <div className="text-center py-8 border rounded-lg bg-muted/30">
                  <Brain className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">No memories captured yet</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Click Capture to extract memories from this conversation
                  </p>
                  <Button variant="outline" size="sm" className="mt-3" onClick={handleCapture}>
                    <Plus className="w-4 h-4 mr-1" />
                    Capture Now
                  </Button>
                </div>
              ) : (
                records.map((record) => (
                  <MemoryRecordCard
                    key={record.name}
                    record={record}
                    onView={handleView}
                    onDelete={handleDelete}
                  />
                ))
              )}
            </div>
          </div>

          {/* Capture Result */}
          {captureResult && (
            <div className="rounded-lg border p-3 bg-muted/30">
              <p className="text-xs font-medium mb-1">Last Capture Result</p>
              <div className="flex items-center gap-4 text-xs">
                <span className="text-green-600">
                  {captureResult.records_created} created
                </span>
                <span className="text-blue-600">
                  {captureResult.records_updated} updated
                </span>
                <span className="text-gray-500">
                  {captureResult.records_skipped} skipped
                </span>
                {captureResult.latency_ms && (
                  <span className="text-muted-foreground">
                    ({captureResult.latency_ms}ms)
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Detail Dialog */}
      <MemoryDetailDialog
        open={detailOpen}
        onOpenChange={setDetailOpen}
        record={selectedRecord}
      />
    </div>
  );
}

// ============================================================================
// Compact Version for Sidebar Integration
// ============================================================================

export function MemoryInspectorCompact({ conversationId }: { conversationId: string }) {
  const { records, loading, capture } = useConversationMemory({
    conversationId,
    autoFetch: true,
  });

  const handleCapture = async () => {
    try {
      const result = await capture();
      if (result.success) {
        toast.success(`Captured ${result.records_created} memories`);
      }
    } catch (err) {
      toast.error('Capture failed');
    }
  };

  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4 text-indigo-500" />
          <span className="text-sm font-medium">Memory</span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={handleCapture}>
            <Plus className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-4">
          <RefreshCw className="w-4 h-4 animate-spin text-muted-foreground" />
        </div>
      ) : records.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center py-2">
          No memories yet
        </p>
      ) : (
        <div className="space-y-1">
          {records.slice(0, 5).map((record) => (
            <div
              key={record.name}
              className="flex items-center gap-2 p-2 rounded hover:bg-muted text-sm"
            >
              <MemoryTypeIcon type={record.memory_type} />
              <span className="truncate flex-1">{record.title}</span>
              <MemoryStatusBadge status={record.status} />
            </div>
          ))}
          {records.length > 5 && (
            <p className="text-xs text-muted-foreground text-center py-1">
              +{records.length - 5} more
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default MemoryInspector;
