import { useEffect, useMemo, useState } from 'react';
import {
  ArrowUpDown,
  CheckCircle2,
  ExternalLink,
  KeyRound,
  Link2,
  Loader2,
  Plug,
  Plus,
  Unlink,
} from 'lucide-react';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
  HeaderContext,
} from '@tanstack/react-table';
import { FilterBar, PageLayout, StatusDot, EmptyState } from '@/components/dashboard';
import { Button } from '@/components/ui/button';
import { Combobox } from '@/components/ui/combobox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { toast } from 'sonner';
import { getProviders, type AIProviderDoc } from '@/services/providerApi';
import {
  getConnections,
  getAuthMethods,
  startAuthorization,
  completeAuthorization,
  revokeAuthorization,
  createConnection,
  type ConnectionListItem,
  type AuthMethod,
  type StartAuthorizationResult,
} from '@/services/providerConnectionApi';
import { formatTimeAgo } from '@/utils/time';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

const ADAPTER_TYPES = [
  { value: 'openai_subscription', label: 'OpenAI Subscription' },
  { value: 'openai_community_subscription', label: 'OpenAI Community Subscription' },
  { value: 'kimi_community_subscription', label: 'Kimi For Coding Community' },
  { value: 'google_subscription', label: 'Google Subscription' },
  { value: 'antigravity_subscription', label: 'Antigravity Subscription' },
  { value: 'mock_subscription', label: 'Mock Subscription' },
];

function SortHeader<TData>({
  column,
  label,
}: {
  column: HeaderContext<TData, unknown>['column'];
  label: string;
}) {
  return (
    <Button
      variant="ghost"
      onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
      className="h-8 px-2 font-body text-[13px] font-medium text-steel hover:text-ink hover:bg-paper-deep"
    >
      {label}
      <ArrowUpDown className="ml-2 h-3.5 w-3.5" />
    </Button>
  );
}

function statusVariant(status: string): 'ok' | 'fail' | 'idle' | 'run' {
  switch (status) {
    case 'Active':
      return 'ok';
    case 'Pending Authorization':
      return 'run';
    case 'Expired':
    case 'Error':
      return 'fail';
    default:
      return 'idle';
  }
}

export function AiProviderConnectionsPage() {
  const [connections, setConnections] = useState<ConnectionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sorting, setSorting] = useState<SortingState>([]);

  const [providers, setProviders] = useState<AIProviderDoc[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [newConnection, setNewConnection] = useState({
    connection_name: '',
    provider: '',
    adapter_type: '',
    auth_method: '',
    eligible_models: '["gpt-4o"]',
  });
  const [authMethods, setAuthMethods] = useState<AuthMethod[]>([]);
  const [creating, setCreating] = useState(false);

  const [authorizeOpen, setAuthorizeOpen] = useState(false);
  const [authorizingConnection, setAuthorizingConnection] = useState<ConnectionListItem | null>(null);
  const [authorizeResult, setAuthorizeResult] = useState<StartAuthorizationResult | null>(null);
  const [pastedUrl, setPastedUrl] = useState('');
  const [authorizing, setAuthorizing] = useState(false);
  const [completing, setCompleting] = useState(false);

  const loadConnections = async () => {
    setLoading(true);
    try {
      const data = await getConnections();
      setConnections(data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConnections();
    getProviders().then((response) => {
      const items = Array.isArray(response) ? response : response.items;
      setProviders(items);
    });
  }, []);

  useEffect(() => {
    if (!newConnection.adapter_type) {
      setAuthMethods([]);
      return;
    }
    getAuthMethods(newConnection.adapter_type).then(setAuthMethods);
  }, [newConnection.adapter_type]);

  const providerOptions = useMemo(
    () =>
      providers.map((p) => ({
        value: p.name,
        label: p.provider_name || p.name,
        subtitle: p.provider_brand || '',
      })),
    [providers]
  );

  const handleCreate = async () => {
    if (!newConnection.connection_name.trim() || !newConnection.provider || !newConnection.adapter_type) {
      toast.error('Please fill in all required fields');
      return;
    }
    setCreating(true);
    try {
      await createConnection({
        connection_name: newConnection.connection_name.trim(),
        user: '', // server defaults to current user
        provider: newConnection.provider,
        adapter_type: newConnection.adapter_type,
        auth_method: newConnection.auth_method || authMethods[0]?.method || '',
        eligible_models: newConnection.eligible_models || '[]',
        is_active: 1,
      });
      toast.success('Connection created');
      setCreateOpen(false);
      setNewConnection({
        connection_name: '',
        provider: '',
        adapter_type: '',
        auth_method: '',
        eligible_models: '["gpt-4o"]',
      });
      loadConnections();
    } catch (error) {
      toast.error('Failed to create connection', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setCreating(false);
    }
  };

  const openAuthorize = async (connection: ConnectionListItem) => {
    setAuthorizingConnection(connection);
    setAuthorizeResult(null);
    setPastedUrl('');
    setAuthorizeOpen(true);

    const method = connection.auth_method || connection.auth_methods[0]?.method;
    if (!method) {
      toast.error('No auth method available for this connection');
      return;
    }

    setAuthorizing(true);
    try {
      const result = await startAuthorization(
        connection.name,
        method,
        `${window.location.origin}/huf/sub_oauth`
      );
      setAuthorizeResult(result);
    } catch (error) {
      toast.error('Failed to start authorization', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setAuthorizing(false);
    }
  };

  const handleComplete = async () => {
    if (!authorizingConnection) return;
    setCompleting(true);
    try {
      const payload: Record<string, unknown> = {};
      if (pastedUrl.trim()) {
        payload.pasted_url = pastedUrl.trim();
      }
      const result = await completeAuthorization(authorizingConnection.name, payload);
      toast.success(`Authorization ${result.status || 'completed'}`);
      setAuthorizeOpen(false);
      loadConnections();
    } catch (error) {
      toast.error('Authorization failed', {
        description: getFrappeErrorMessage(error),
      });
    } finally {
      setCompleting(false);
    }
  };

  const handleRevoke = async (connection: ConnectionListItem) => {
    try {
      const result = await revokeAuthorization(connection.name);
      toast.success(`Connection ${result.auth_status.toLowerCase()}`);
      loadConnections();
    } catch (error) {
      toast.error('Failed to revoke connection', {
        description: getFrappeErrorMessage(error),
      });
    }
  };

  const columns = useMemo<ColumnDef<ConnectionListItem>[]>(
    () => [
      {
        accessorKey: 'connection_name',
        header: ({ column }) => <SortHeader column={column} label="Connection" />,
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <Plug className="h-4 w-4 text-steel-soft shrink-0" strokeWidth={1.6} />
            <div>
              <div className="font-body text-[13px] font-semibold text-ink">
                {row.original.connection_name}
              </div>
              <div className="font-mono text-[11px] text-steel-soft">{row.original.adapter_type}</div>
            </div>
          </div>
        ),
      },
      {
        accessorKey: 'provider',
        header: 'Provider',
        cell: ({ row }) => (
          <div className="font-body text-[13px] text-steel">
            {row.original.provider}
          </div>
        ),
      },
      {
        accessorKey: 'auth_status',
        header: 'Status',
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <StatusDot variant={statusVariant(row.original.auth_status)} />
            <span className="font-body text-[13px] text-steel">{row.original.auth_status}</span>
            {row.original.is_expired && row.original.auth_status === 'Active' && (
              <span className="text-[11px] text-destructive">(expired)</span>
            )}
          </div>
        ),
      },
      {
        accessorKey: 'auth_method',
        header: 'Auth Method',
        cell: ({ row }) => (
          <div className="font-mono text-[12px] text-steel">{row.original.auth_method || '-'}</div>
        ),
      },
      {
        accessorKey: 'account_email',
        header: 'Account',
        cell: ({ row }) => (
          <div className="font-body text-[13px] text-steel">
            {row.original.account_email || '-'}
          </div>
        ),
      },
      {
        id: 'modified',
        header: ({ column }) => <SortHeader column={column} label="Modified" />,
        cell: ({ row }) => (
          <div className="font-mono text-[12px] text-steel">
            {formatTimeAgo(row.original.modified ?? null)}
          </div>
        ),
        sortingFn: (rowA, rowB) => {
          const timeA = rowA.original.modified ? new Date(rowA.original.modified).getTime() : 0;
          const timeB = rowB.original.modified ? new Date(rowB.original.modified).getTime() : 0;
          return timeA - timeB;
        },
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => {
          const conn = row.original;
          const canAuthorize = conn.auth_status !== 'Active';
          return (
            <div className="flex items-center justify-end gap-1">
              {canAuthorize ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => openAuthorize(conn)}
                  disabled={authorizing && authorizingConnection?.name === conn.name}
                >
                  {authorizing && authorizingConnection?.name === conn.name ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Link2 className="h-4 w-4" />
                  )}
                  <span className="ml-1">Authorize</span>
                </Button>
              ) : (
                <Button variant="ghost" size="sm" onClick={() => handleRevoke(conn)}>
                  <Unlink className="h-4 w-4" />
                  <span className="ml-1">Revoke</span>
                </Button>
              )}
            </div>
          );
        },
      },
    ],
    [authorizing, authorizingConnection]
  );

  const filteredConnections = useMemo(() => {
    if (!search.trim()) return connections;
    const term = search.toLowerCase();
    return connections.filter(
      (c) =>
        c.connection_name.toLowerCase().includes(term) ||
        c.provider.toLowerCase().includes(term) ||
        c.adapter_type.toLowerCase().includes(term) ||
        (c.account_email || '').toLowerCase().includes(term)
    );
  }, [connections, search]);

  const table = useReactTable({
    data: filteredConnections,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: { sorting },
  });

  const authMethodOptions = useMemo(
    () => authMethods.map((m) => ({ value: m.method, label: m.label || m.method })),
    [authMethods]
  );

  return (
    <PageLayout
      title="Subscription Connections"
      subtitle="Manage per-user OAuth and device-code connections for subscription-backed AI providers."
      filters={
        <FilterBar
          searchPlaceholder="Search connections..."
          searchValue={search}
          onSearchChange={setSearch}
          actions={
            <Button variant="display" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Add Connection
            </Button>
          }
        />
      }
    >
      <div className="w-full">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
          </div>
        ) : filteredConnections.length === 0 ? (
          <EmptyState
            icon={KeyRound}
            title="No subscription connections"
            description="Add a connection to authorize subscription-backed providers like OpenAI Community or Kimi For Coding."
            action={{ label: 'Add connection', onClick: () => setCreateOpen(true) }}
          />
        ) : (
          <div className="border border-line bg-panel">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id}>
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Create Connection Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle>Add Subscription Connection</DialogTitle>
            <DialogDescription>
              Create a per-user connection for a subscription-backed provider.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="connection_name">
                Connection Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="connection_name"
                placeholder="e.g. My OpenAI Community"
                value={newConnection.connection_name}
                onChange={(e) => setNewConnection({ ...newConnection, connection_name: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label>AI Provider <span className="text-destructive">*</span></Label>
              <Combobox
                options={providerOptions}
                value={newConnection.provider}
                onValueChange={(value) => setNewConnection({ ...newConnection, provider: value })}
                placeholder="Select provider..."
              />
            </div>

            <div className="space-y-2">
              <Label>Adapter Type <span className="text-destructive">*</span></Label>
              <Select
                value={newConnection.adapter_type}
                onValueChange={(value) =>
                  setNewConnection({ ...newConnection, adapter_type: value, auth_method: '' })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select adapter..." />
                </SelectTrigger>
                <SelectContent>
                  {ADAPTER_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Auth Method</Label>
              <Select
                value={newConnection.auth_method}
                onValueChange={(value) => setNewConnection({ ...newConnection, auth_method: value })}
                disabled={authMethodOptions.length === 0}
              >
                <SelectTrigger>
                  <SelectValue placeholder={authMethodOptions.length === 0 ? 'Select adapter first' : 'Select auth method...'} />
                </SelectTrigger>
                <SelectContent>
                  {authMethodOptions.map((m) => (
                    <SelectItem key={m.value} value={m.value}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="eligible_models">Eligible Models (JSON array)</Label>
              <Textarea
                id="eligible_models"
                value={newConnection.eligible_models}
                onChange={(e) => setNewConnection({ ...newConnection, eligible_models: e.target.value })}
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={creating}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={creating}>
              {creating ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
              Create Connection
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Authorize Dialog */}
      <Dialog open={authorizeOpen} onOpenChange={setAuthorizeOpen}>
        <DialogContent className="sm:max-w-[560px]">
          <DialogHeader>
            <DialogTitle>Authorize {authorizingConnection?.connection_name}</DialogTitle>
            <DialogDescription>
              Complete the provider flow to link your subscription.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {authorizing ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
              </div>
            ) : !authorizeResult ? (
              <p className="text-sm text-steel">Could not start authorization. Check site config flags.</p>
            ) : (
              <>
                {authorizeResult.auth_url && (
                  <div className="space-y-2">
                    <Label>Authorization URL</Label>
                    <div className="flex gap-2">
                      <Input readOnly value={authorizeResult.auth_url} />
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={() => window.open(authorizeResult.auth_url, '_blank')}
                      >
                        <ExternalLink className="h-4 w-4" />
                      </Button>
                    </div>
                    <p className="text-xs text-steel">
                      Open the URL, authorize, then paste the final browser URL below.
                    </p>
                  </div>
                )}

                {authorizeResult.user_code && (
                  <div className="space-y-2 rounded-md border bg-muted/40 p-3">
                    <div className="flex items-center justify-between">
                      <Label>User Code</Label>
                      <span className="font-mono text-lg font-bold">{authorizeResult.user_code}</span>
                    </div>
                    {authorizeResult.verification_uri_complete && (
                      <a
                        href={authorizeResult.verification_uri_complete}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                      >
                        Open verification page <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                    <p className="text-xs text-steel">
                      Enter the code on the provider site, then click Complete below.
                    </p>
                  </div>
                )}

                {authorizeResult.auth_url && (
                  <div className="space-y-2">
                    <Label htmlFor="pasted_url">Pasted Callback URL</Label>
                    <Textarea
                      id="pasted_url"
                      placeholder="https://...?code=...&state=..."
                      value={pastedUrl}
                      onChange={(e) => setPastedUrl(e.target.value)}
                      rows={3}
                    />
                  </div>
                )}
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAuthorizeOpen(false)} disabled={completing}>
              Cancel
            </Button>
            <Button onClick={handleComplete} disabled={completing || authorizing}>
              {completing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-2" />}
              Complete Authorization
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageLayout>
  );
}

export default AiProviderConnectionsPage;
