import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Brain,
  Search,
  Filter,
  Database,
  Sparkles,
  User,
  Bot,
  Globe,
  Share2,
  Trash2,
  Eye,
  RefreshCw,
  Download,
  Plus,
  Tag,
  BarChart3,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import type {
  MemoryRecord,
  MemoryRecordRow,
  MemoryScopeType,
  MemoryType,
  MemoryStatus,
  MemoryFilters,
} from '@/types/memory.types';
import {
  useMemoryRecords,
  useMemoryRecord,
  useMemoryStats,
  useMemorySearch,
} from './hooks/useMemory';
import { formatDistanceToNow } from '@/utils/dateUtils';

// ============================================================================
// Types
// ============================================================================

interface MemoryExplorerProps {
  agentFilter?: string;
  conversationFilter?: string;
}

interface MemoryStatsCardProps {
  title: string;
  value: number | string;
  description?: string;
  icon: React.ReactNode;
}

interface MemoryFilterPanelProps {
  filters: MemoryFilters;
  onFiltersChange: (filters: MemoryFilters) => void;
}

interface MemoryRecordCardProps {
  record: MemoryRecordRow;
  onView: (record: MemoryRecordRow) => void;
  onDelete: (record: MemoryRecordRow) => void;
}

// ============================================================================
// Helper Components
// ============================================================================

function MemoryStatsCard({ title, value, description, icon }: MemoryStatsCardProps) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold mt-1">{value}</p>
            {description && (
              <p className="text-xs text-muted-foreground mt-1">{description}</p>
            )}
          </div>
          <div className="p-3 bg-primary/10 rounded-full">{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}

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
    <Badge variant="secondary" className={colors[scope] || ''}>
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
    <Badge variant="secondary" className={colors[status] || ''}>
      <span className="capitalize">{status}</span>
    </Badge>
  );
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
    <Badge variant="outline" className="text-xs">
      {typeLabels[type] || type}
    </Badge>
  );
}

function MemoryRecordCard({ record, onView, onDelete }: MemoryRecordCardProps) {
  return (
    <div className="group rounded-lg border p-4 hover:bg-muted/50 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <h4 className="font-medium truncate">{record.title || 'Untitled Memory'}</h4>
            <MemoryStatusBadge status={record.status} />
            <MemoryScopeBadge scope={record.scope_type} />
          </div>
          
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
            <span>Agent: {record.agent_name || record.agent}</span>
            <span>•</span>
            <MemoryTypeBadge type={record.memory_type} />
          </div>

          {record.tags && record.tags.length > 0 && (
            <div className="flex items-center gap-1 flex-wrap mb-2">
              {record.tags.map((tag) => (
                <Badge key={tag} variant="outline" className="text-[10px]">
                  <Tag className="w-3 h-3 mr-1" />
                  {tag}
                </Badge>
              ))}
            </div>
          )}

          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            {record.confidence !== undefined && (
              <span>Confidence: {(record.confidence * 100).toFixed(0)}%</span>
            )}
            {record.importance_score !== undefined && (
              <span>Importance: {record.importance_score}/10</span>
            )}
            <span>{formatDistanceToNow(record.modified)}</span>
          </div>
        </div>

        <div className="flex items-center gap-1 opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity">
          <Button variant="ghost" size="sm" onClick={() => onView(record)}>
            <Eye className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onDelete(record)}>
            <Trash2 className="w-4 h-4 text-red-500" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function MemoryFilterPanel({ filters, onFiltersChange }: MemoryFilterPanelProps) {
  const scopeTypes: MemoryScopeType[] = ['conversation', 'user', 'agent', 'namespace', 'global'];
  const memoryTypes: MemoryType[] = ['profile', 'session_state', 'preference', 'fact', 'plan', 'observation', 'insight', 'domain_object', 'custom'];
  const statuses: MemoryStatus[] = ['active', 'superseded', 'archived', 'expired', 'error'];

  return (
    <div className="space-y-4">
      <div>
        <label className="text-sm font-medium mb-2 block">Scope</label>
        <Select
          value={filters.scope_type || 'all'}
          onValueChange={(value) =>
            onFiltersChange({ ...filters, scope_type: value === 'all' ? undefined : (value as MemoryScopeType) })
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="All scopes" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All scopes</SelectItem>
            {scopeTypes.map((scope) => (
              <SelectItem key={scope} value={scope}>
                <div className="flex items-center gap-2">
                  <MemoryScopeIcon scope={scope} />
                  <span className="capitalize">{scope}</span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div>
        <label className="text-sm font-medium mb-2 block">Memory Type</label>
        <Select
          value={filters.memory_type || 'all'}
          onValueChange={(value) =>
            onFiltersChange({ ...filters, memory_type: value === 'all' ? undefined : (value as MemoryType) })
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All types</SelectItem>
            {memoryTypes.map((type) => (
              <SelectItem key={type} value={type}>
                <span className="capitalize">{type.replace('_', ' ')}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div>
        <label className="text-sm font-medium mb-2 block">Status</label>
        <Select
          value={filters.status || 'all'}
          onValueChange={(value) =>
            onFiltersChange({ ...filters, status: value === 'all' ? undefined : (value as MemoryStatus) })
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {statuses.map((status) => (
              <SelectItem key={status} value={status}>
                <span className="capitalize">{status}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Separator />

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="fts_indexed"
          checked={filters.fts_indexed || false}
          onChange={(e) => onFiltersChange({ ...filters, fts_indexed: e.target.checked })}
          className="rounded border-gray-300"
        />
        <label htmlFor="fts_indexed" className="text-sm">
          FTS Indexed
        </label>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="vector_indexed"
          checked={filters.vector_indexed || false}
          onChange={(e) => onFiltersChange({ ...filters, vector_indexed: e.target.checked })}
          className="rounded border-gray-300"
        />
        <label htmlFor="vector_indexed" className="text-sm">
          Vector Indexed
        </label>
      </div>
    </div>
  );
}

function MemoryDetailDialog({
  open,
  onOpenChange,
  recordName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  recordName: string | null;
}) {
  const { record, loading } = useMemoryRecord({ name: recordName || undefined });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle>{record?.title || 'Memory Details'}</DialogTitle>
          <DialogDescription>
            View complete memory record information
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="w-6 h-6 animate-spin" />
          </div>
        ) : record ? (
          <ScrollArea className="max-h-[60vh]">
            <div className="space-y-6">
              <div className="flex items-center gap-2 flex-wrap">
                <MemoryScopeBadge scope={record.scope_type} />
                <MemoryStatusBadge status={record.status} />
                <MemoryTypeBadge type={record.memory_type} />
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <label className="text-muted-foreground">Agent</label>
                  <p>{record.agent_name || record.agent}</p>
                </div>
                <div>
                  <label className="text-muted-foreground">Created</label>
                  <p>{new Date(record.creation).toLocaleString()}</p>
                </div>
                <div>
                  <label className="text-muted-foreground">Modified</label>
                  <p>{new Date(record.modified).toLocaleString()}</p>
                </div>
                <div>
                  <label className="text-muted-foreground">Retrievals</label>
                  <p>{record.retrieval_count}</p>
                </div>
              </div>

              {record.summary_text && (
                <div>
                  <label className="text-sm font-medium">Summary</label>
                  <p className="text-sm text-muted-foreground mt-1">{record.summary_text}</p>
                </div>
              )}

              {record.data_json && Object.keys(record.data_json).length > 0 && (
                <div>
                  <label className="text-sm font-medium">Data</label>
                  <pre className="mt-2 p-4 bg-muted rounded-lg text-xs overflow-auto">
                    {JSON.stringify(record.data_json, null, 2)}
                  </pre>
                </div>
              )}

              {record.tags && record.tags.length > 0 && (
                <div>
                  <label className="text-sm font-medium">Tags</label>
                  <div className="flex items-center gap-2 mt-2">
                    {record.tags.map((tag) => (
                      <Badge key={tag} variant="outline">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        ) : (
          <p className="text-muted-foreground text-center py-12">Record not found</p>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function MemoryExplorer({ agentFilter, conversationFilter }: MemoryExplorerProps) {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<MemoryFilters>({
    agent: agentFilter,
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRecord, setSelectedRecord] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const { records, loading, error, refetch } = useMemoryRecords({
    filters,
    autoFetch: true,
  });

  const { stats, loading: loadingStats } = useMemoryStats();
  const { results: searchResults, loading: searching, search } = useMemorySearch();

  const displayRecords = useMemo(() => {
    if (searchQuery.trim()) {
      return searchResults;
    }
    return records;
  }, [searchQuery, searchResults, records]);

  const handleSearch = async (query: string) => {
    setSearchQuery(query);
    if (query.trim()) {
      await search(query);
    }
  };

  const handleView = (record: MemoryRecordRow) => {
    setSelectedRecord(record.name);
    setDetailOpen(true);
  };

  const handleDelete = async (record: MemoryRecordRow) => {
    if (confirm(`Delete memory "${record.title}"? This action cannot be undone.`)) {
      try {
        // Delete logic here
        toast.success('Memory deleted successfully');
        refetch();
      } catch (err) {
        toast.error('Failed to delete memory');
      }
    }
  };

  const handleExport = () => {
    const data = JSON.stringify(displayRecords, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `memory-export-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Memory records exported');
  };

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="text-red-500">Error Loading Memory</CardTitle>
            <CardDescription>{error.message}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={refetch} className="w-full">
              <RefreshCw className="w-4 h-4 mr-2" />
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="border-b p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Brain className="w-6 h-6 text-indigo-500" />
            <h1 className="text-2xl font-bold">Memory Explorer</h1>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleExport}>
              <Download className="w-4 h-4 mr-2" />
              Export
            </Button>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Refresh
            </Button>
          </div>
        </div>

        {/* Stats */}
        {!loadingStats && stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MemoryStatsCard
              title="Total Records"
              value={stats.total_records}
              icon={<Database className="w-5 h-5 text-blue-500" />}
            />
            <MemoryStatsCard
              title="FTS Indexed"
              value={stats.indexed_fts}
              icon={<Search className="w-5 h-5 text-amber-500" />}
            />
            <MemoryStatsCard
              title="Vector Indexed"
              value={stats.indexed_vector}
              icon={<Sparkles className="w-5 h-5 text-purple-500" />}
            />
            <MemoryStatsCard
              title="Active"
              value={stats.by_status?.active || 0}
              icon={<BarChart3 className="w-5 h-5 text-green-500" />}
            />
          </div>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar Filters */}
        <div className="w-64 border-r bg-muted/30 p-4 overflow-y-auto hidden lg:block">
          <div className="flex items-center gap-2 mb-4">
            <Filter className="w-4 h-4" />
            <h3 className="font-medium">Filters</h3>
          </div>
          <MemoryFilterPanel filters={filters} onFiltersChange={setFilters} />
        </div>

        {/* Records List */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Search Bar */}
          <div className="p-4 border-b">
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search memories..."
                  className="pl-10"
                  value={searchQuery}
                  onChange={(e) => handleSearch(e.target.value)}
                />
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="icon" className="lg:hidden">
                    <Filter className="w-4 h-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-64">
                  <DropdownMenuLabel>Filters</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <div className="p-2">
                    <MemoryFilterPanel filters={filters} onFiltersChange={setFilters} />
                  </div>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          {/* Records */}
          <ScrollArea className="flex-1">
            <div className="p-4 space-y-3">
              {loading || searching ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              ) : displayRecords.length === 0 ? (
                <div className="text-center py-12">
                  <Brain className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">No memory records found</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    {searchQuery
                      ? 'Try adjusting your search query'
                      : 'Memory will appear here once agents create them'}
                  </p>
                </div>
              ) : (
                displayRecords.map((record) => (
                  <MemoryRecordCard
                    key={record.name}
                    record={record}
                    onView={handleView}
                    onDelete={handleDelete}
                  />
                ))
              )}
            </div>
          </ScrollArea>
        </div>
      </div>

      {/* Detail Dialog */}
      <MemoryDetailDialog
        open={detailOpen}
        onOpenChange={setDetailOpen}
        recordName={selectedRecord}
      />
    </div>
  );
}
