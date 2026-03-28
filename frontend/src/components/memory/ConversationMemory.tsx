import { useState, useCallback } from 'react';
import {
  Brain,
  ChevronDown,
  ChevronRight,
  Sparkles,
  RefreshCw,
  Database,
  Tag,
  Clock,
  CheckCircle2,
  AlertCircle,
  Plus,
  ExternalLink,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import type { MemoryRecordRow, MemoryCaptureResult } from '@/types/memory.types';
import { useConversationMemory } from './hooks/useMemory';

// ============================================================================
// Types
// ============================================================================

interface ConversationMemoryProps {
  conversationId: string;
  agentName?: string;
  className?: string;
}

interface MemoryCaptureButtonProps {
  conversationId: string;
  onCapture?: (result: MemoryCaptureResult) => void;
  variant?: 'default' | 'outline' | 'ghost';
  size?: 'default' | 'sm' | 'lg' | 'icon';
}

interface MemoryRecordMiniProps {
  record: MemoryRecordRow;
  onView?: (record: MemoryRecordRow) => void;
}

interface ConversationMemoryPanelProps {
  conversationId: string;
  agentName?: string;
}

interface MemoryStatusIndicatorProps {
  count: number;
  lastCaptureAt?: string;
}

// ============================================================================
// Helper Components
// ============================================================================

function MemoryStatusIndicator({ count, lastCaptureAt }: MemoryStatusIndicatorProps) {
  if (count === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <AlertCircle className="w-4 h-4" />
        <span>No memories captured yet</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 text-sm text-emerald-600">
      <CheckCircle2 className="w-4 h-4" />
      <span>{count} memory{count !== 1 ? 'ies' : 'y'} captured</span>
      {lastCaptureAt && (
        <span className="text-muted-foreground">
          • Last capture: {new Date(lastCaptureAt).toLocaleTimeString()}
        </span>
      )}
    </div>
  );
}

function MemoryRecordMini({ record, onView }: MemoryRecordMiniProps) {
  const scopeColors: Record<string, string> = {
    conversation: 'bg-blue-100 text-blue-800',
    user: 'bg-green-100 text-green-800',
    agent: 'bg-purple-100 text-purple-800',
    namespace: 'bg-amber-100 text-amber-800',
    global: 'bg-rose-100 text-rose-800',
  };

  const statusIcons: Record<string, React.ReactNode> = {
    active: <CheckCircle2 className="w-3 h-3 text-emerald-500" />,
    superseded: <Clock className="w-3 h-3 text-gray-400" />,
    archived: <Database className="w-3 h-3 text-slate-400" />,
    expired: <AlertCircle className="w-3 h-3 text-red-400" />,
    error: <AlertCircle className="w-3 h-3 text-red-600" />,
  };

  return (
    <div
      className="group flex items-start gap-3 p-3 rounded-lg border hover:bg-muted/50 transition-colors cursor-pointer"
      onClick={() => onView?.(record)}
    >
      <div className="mt-0.5">{statusIcons[record.status] || statusIcons.active}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-sm truncate">{record.title || 'Untitled'}</span>
          <Badge
            variant="secondary"
            className={`text-[10px] px-1.5 py-0 ${scopeColors[record.scope_type] || ''}`}
          >
            {record.scope_type}
          </Badge>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="capitalize">{record.memory_type.replace('_', ' ')}</span>
          {record.tags && record.tags.length > 0 && (
            <>
              <span>•</span>
              <div className="flex items-center gap-1">
                <Tag className="w-3 h-3" />
                {record.tags.slice(0, 2).join(', ')}
                {record.tags.length > 2 && ` +${record.tags.length - 2}`}
              </div>
            </>
          )}
        </div>
      </div>
      <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
    </div>
  );
}

// ============================================================================
// Capture Button Component
// ============================================================================

export function MemoryCaptureButton({
  conversationId,
  onCapture,
  variant = 'outline',
  size = 'sm',
}: MemoryCaptureButtonProps) {
  const [capturing, setCapturing] = useState(false);
  const { capture } = useConversationMemory({ conversationId, autoFetch: false });

  const handleCapture = useCallback(async () => {
    setCapturing(true);
    try {
      const result = await capture();
      toast.success(
        `Memory capture complete: ${result.records_created} created, ${result.records_updated} updated`
      );
      onCapture?.(result);
    } catch (err) {
      toast.error('Failed to capture memory');
    } finally {
      setCapturing(false);
    }
  }, [capture, onCapture]);

  return (
    <Button
      variant={variant}
      size={size}
      onClick={handleCapture}
      disabled={capturing}
    >
      {capturing ? (
        <>
          <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
          Capturing...
        </>
      ) : (
        <>
          <Sparkles className="w-4 h-4 mr-2" />
          Capture Memory
        </>
      )}
    </Button>
  );
}

// ============================================================================
// Memory Panel Component (Collapsible Sidebar)
// ============================================================================

export function ConversationMemoryPanel({ conversationId, agentName }: ConversationMemoryPanelProps) {
  const [open, setOpen] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<MemoryRecordRow | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const { records, loading, capture, captureResult, fetchRecords } = useConversationMemory({
    conversationId,
    autoFetch: true,
  });

  const handleCapture = useCallback(async () => {
    try {
      await capture();
      toast.success('Memory captured successfully');
    } catch (err) {
      toast.error('Failed to capture memory');
    }
  }, [capture]);

  const handleView = useCallback((record: MemoryRecordRow) => {
    setSelectedRecord(record);
    setDetailOpen(true);
  }, []);

  return (
    <Card className="w-full">
      <Collapsible open={open} onOpenChange={setOpen}>
        <CardHeader className="p-4">
          <div className="flex items-center justify-between">
            <CollapsibleTrigger asChild>
              <Button variant="ghost" className="w-full justify-start p-0 h-auto hover:bg-transparent">
                <div className="flex items-center gap-2">
                  <Brain className="w-5 h-5 text-indigo-500" />
                  <CardTitle className="text-base">Conversation Memory</CardTitle>
                  {records.length > 0 && (
                    <Badge variant="secondary" className="ml-2">{records.length}</Badge>
                  )}
                  {open ? (
                    <ChevronDown className="w-4 h-4 ml-2 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="w-4 h-4 ml-2 text-muted-foreground" />
                  )}
                </div>
              </Button>
            </CollapsibleTrigger>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={(e) => {
                  e.stopPropagation();
                  fetchRecords();
                }}
              >
                <RefreshCw className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </CardHeader>

        <CollapsibleContent>
          <CardContent className="pt-0 px-4 pb-4">
            <div className="space-y-3">
              {/* Status */}
              <MemoryStatusIndicator
                count={records.length}
                lastCaptureAt={captureResult?.latency_ms ? new Date().toISOString() : undefined}
              />

              <Separator />

              {/* Capture Button */}
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={handleCapture}
              >
                <Sparkles className="w-4 h-4 mr-2" />
                Capture Memory Now
              </Button>

              {/* Records List */}
              <ScrollArea className="max-h-[300px]">
                <div className="space-y-2">
                  {loading ? (
                    <div className="flex items-center justify-center py-8">
                      <RefreshCw className="w-5 h-5 animate-spin text-muted-foreground" />
                    </div>
                  ) : records.length === 0 ? (
                    <div className="text-center py-8 text-sm text-muted-foreground">
                      <Brain className="w-8 h-8 mx-auto mb-2 opacity-50" />
                      <p>No memories captured yet</p>
                      <p className="text-xs mt-1">
                        Memories will appear here when the agent captures them
                      </p>
                    </div>
                  ) : (
                    records.map((record) => (
                      <MemoryRecordMini
                        key={record.name}
                        record={record}
                        onView={handleView}
                      />
                    ))
                  )}
                </div>
              </ScrollArea>
            </div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>

      {/* Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{selectedRecord?.title || 'Memory Details'}</DialogTitle>
            <DialogDescription>
              Memory record from this conversation
            </DialogDescription>
          </DialogHeader>

          {selectedRecord && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Badge variant="secondary">{selectedRecord.scope_type}</Badge>
                <Badge variant="outline">{selectedRecord.memory_type}</Badge>
                <Badge
                  variant={selectedRecord.status === 'active' ? 'default' : 'secondary'}
                >
                  {selectedRecord.status}
                </Badge>
              </div>

              <div className="text-sm space-y-2">
                <div>
                  <span className="text-muted-foreground">Agent: </span>
                  {selectedRecord.agent_name || selectedRecord.agent}
                </div>
                {selectedRecord.confidence !== undefined && (
                  <div>
                    <span className="text-muted-foreground">Confidence: </span>
                    {(selectedRecord.confidence * 100).toFixed(0)}%
                  </div>
                )}
                {selectedRecord.importance_score !== undefined && (
                  <div>
                    <span className="text-muted-foreground">Importance: </span>
                    {selectedRecord.importance_score}/10
                  </div>
                )}
                <div>
                  <span className="text-muted-foreground">Created: </span>
                  {new Date(selectedRecord.creation).toLocaleString()}
                </div>
              </div>

              {selectedRecord.tags && selectedRecord.tags.length > 0 && (
                <div>
                  <span className="text-sm text-muted-foreground">Tags: </span>
                  <div className="flex items-center gap-1 mt-1 flex-wrap">
                    {selectedRecord.tags.map((tag) => (
                      <Badge key={tag} variant="outline" className="text-xs">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              <Button
                variant="outline"
                className="w-full"
                onClick={() => {
                  // Navigate to memory explorer
                  window.open(`/memory/${selectedRecord.name}`, '_blank');
                }}
              >
                <ExternalLink className="w-4 h-4 mr-2" />
                View in Memory Explorer
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ============================================================================
// Inline Memory Indicator (Compact)
// ============================================================================

export function ConversationMemoryIndicator({ conversationId }: { conversationId: string }) {
  const { records, loading } = useConversationMemory({ conversationId, autoFetch: true });

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <RefreshCw className="w-3 h-3 animate-spin" />
        <span>Loading memory...</span>
      </div>
    );
  }

  if (records.length === 0) {
    return null;
  }

  return (
    <div className="flex items-center gap-2 text-xs">
      <Brain className="w-3 h-3 text-indigo-500" />
      <span className="text-muted-foreground">
        {records.length} memory record{records.length !== 1 ? 's' : ''}
      </span>
    </div>
  );
}

// ============================================================================
// Memory Sidebar for Chat UI
// ============================================================================

export function MemorySidebar({ conversationId, agentName }: ConversationMemoryProps) {
  const [activeTab, setActiveTab] = useState<'memories' | 'capture'>('memories');
  const { records, loading, capture, fetchRecords } = useConversationMemory({
    conversationId,
    autoFetch: true,
  });

  const handleCapture = useCallback(async () => {
    try {
      await capture();
      toast.success('Memory captured successfully');
      setActiveTab('memories');
    } catch (err) {
      toast.error('Failed to capture memory');
    }
  }, [capture]);

  return (
    <div className="w-80 border-l bg-muted/30 h-full flex flex-col">
      <div className="p-4 border-b">
        <div className="flex items-center gap-2 mb-4">
          <Brain className="w-5 h-5 text-indigo-500" />
          <h2 className="font-semibold">Memory</h2>
          {records.length > 0 && (
            <Badge variant="secondary">{records.length}</Badge>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant={activeTab === 'memories' ? 'default' : 'ghost'}
            size="sm"
            className="flex-1"
            onClick={() => setActiveTab('memories')}
          >
            <Database className="w-4 h-4 mr-2" />
            Records
          </Button>
          <Button
            variant={activeTab === 'capture' ? 'default' : 'ghost'}
            size="sm"
            className="flex-1"
            onClick={() => setActiveTab('capture')}
          >
            <Plus className="w-4 h-4 mr-2" />
            Capture
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-4">
          {activeTab === 'memories' ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  {records.length} record{records.length !== 1 ? 's' : ''}
                </span>
                <Button variant="ghost" size="icon" className="h-8 w-8" onClick={fetchRecords}>
                  <RefreshCw className="w-4 h-4" />
                </Button>
              </div>

              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <RefreshCw className="w-5 h-5 animate-spin text-muted-foreground" />
                </div>
              ) : records.length === 0 ? (
                <div className="text-center py-8 text-sm text-muted-foreground">
                  <Brain className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p>No memories yet</p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-3"
                    onClick={() => setActiveTab('capture')}
                  >
                    <Plus className="w-4 h-4 mr-2" />
                    Capture Now
                  </Button>
                </div>
              ) : (
                records.map((record) => (
                  <MemoryRecordMini key={record.name} record={record} />
                ))
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Manually trigger memory capture for this conversation.
              </p>

              <Button
                className="w-full"
                onClick={handleCapture}
              >
                <Sparkles className="w-4 h-4 mr-2" />
                Capture Memory Now
              </Button>

              <div className="text-xs text-muted-foreground space-y-2">
                <p>This will:</p>
                <ul className="list-disc list-inside space-y-1">
                  <li>Analyze the conversation</li>
                  <li>Extract structured memory</li>
                  <li>Store according to agent policy</li>
                </ul>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

// ============================================================================
// Main Export Component
// ============================================================================

export function ConversationMemory({ conversationId, agentName, className }: ConversationMemoryProps) {
  return (
    <div className={className}>
      <ConversationMemoryPanel conversationId={conversationId} agentName={agentName} />
    </div>
  );
}

// Named exports for individual components
export {
  MemoryCaptureButton,
  ConversationMemoryPanel,
  MemorySidebar,
  ConversationMemoryIndicator,
  MemoryRecordMini,
};

export default ConversationMemory;
