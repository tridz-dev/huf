import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Loader2, Plus, RefreshCw, Search } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { usePermissions } from '@/contexts/PermissionsContext';
import { useSocket } from '@/contexts/SocketContext';
import {
  deleteTemplate, errorText, isBridgeUnavailable, listTemplateDrafts, listTemplates, syncTemplates,
  type TemplateDetail, type TemplateDraft, type WhatsAppTemplate,
} from '@/services/whatsappApi';
import { BridgeUnavailable, LoadError } from './BridgeUnavailable';
import { CategoryChangeBadge, QualityBadge, StatusBadge } from './TemplateBadges';
import { DraftsPanel } from './DraftsPanel';
import { ManagerLink } from './ManagerLink';
import { SendTemplateDialog } from './SendTemplateDialog';
import { TemplateDetailPane } from './TemplateDetailPane';
import { TemplateEditor } from './TemplateEditor';
import {
  ALL_OPTION, OPEN_DRAFT_STATUSES, TEMPLATE_STATUSES, filterTemplates, statusInfo, statusToastText, type TemplateFilters,
} from './templateModel';

const STATUS_EVENT = 'whatsapp_template_status';

type View = { kind: 'browse' } | { kind: 'create' } | { kind: 'edit'; detail: TemplateDetail };

export function TemplatesTab({ gateway }: { gateway?: string }) {
  const { hufRole } = usePermissions();
  const isAdmin = hufRole === 'Huf Admin';
  const socket = useSocket();

  const [rows, setRows] = useState<WhatsAppTemplate[]>([]);
  const [manager, setManager] = useState({ url: '', businessId: '' });
  const [drafts, setDrafts] = useState<TemplateDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [unavailable, setUnavailable] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [view, setView] = useState<View>({ kind: 'browse' });
  const [section, setSection] = useState('templates');
  const [selected, setSelected] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [filters, setFilters] = useState<TemplateFilters>({ search: '', status: ALL_OPTION, category: ALL_OPTION, language: ALL_OPTION });
  const [toDelete, setToDelete] = useState<WhatsAppTemplate | null>(null);
  const [toSend, setToSend] = useState<WhatsAppTemplate | null>(null);

  const loadDrafts = useCallback(async () => {
    if (!gateway) return;
    const res = await listTemplateDrafts(gateway);
    if (res.success) setDrafts(res.drafts);
  }, [gateway]);

  const load = useCallback(async () => {
    if (!gateway) {
      setRows([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    const res = await listTemplates(gateway);
    if (res.success) {
      setRows(res.templates);
      setManager({ url: res.manager_url ?? '', businessId: res.business_id ?? '' });
      setUnavailable(false);
    } else if (isBridgeUnavailable(res)) {
      setUnavailable(true);
    } else {
      setError(errorText(res));
    }
    setLoading(false);
  }, [gateway]);

  useEffect(() => {
    void load();
    void loadDrafts();
  }, [load, loadDrafts]);

  // Refresh and tell the user when WhatsApp reviews a template.
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  useEffect(() => {
    if (!socket) return;
    const handler = (data: { template?: string; status?: string }) => {
      if (!data?.template) return;
      const known = rowsRef.current.find((r) => r.name === data.template);
      const toastInfo = statusToastText(known?.template_name || data.template, data.status);
      if (toastInfo.tone === 'success') toast.success(toastInfo.text);
      else if (toastInfo.tone === 'error') toast.error(toastInfo.text);
      else toast(toastInfo.text);
      void load();
      void loadDrafts();
      setRefreshKey((k) => k + 1);
    };
    socket.on(STATUS_EVENT, handler);
    return () => {
      socket.off(STATUS_EVENT, handler);
    };
  }, [socket, load, loadDrafts, rowsRef]);

  const sync = async () => {
    if (!gateway) return;
    setSyncing(true);
    const res = await syncTemplates(gateway);
    setSyncing(false);
    if (res.success) {
      toast.success(`Templates synced: ${res.imported ?? 0} imported, ${res.updated ?? 0} updated`);
      void load();
    } else if (isBridgeUnavailable(res)) setUnavailable(true);
    else toast.error(errorText(res));
  };

  const confirmDelete = async () => {
    if (!toDelete) return;
    const res = await deleteTemplate(toDelete.name);
    setToDelete(null);
    if (res.success) {
      toast.success('Template deleted');
      setSelected('');
      void load();
    } else toast.error(errorText(res));
  };

  const filtered = useMemo(() => filterTemplates(rows, filters), [rows, filters]);
  const languages = useMemo(() => [...new Set(rows.map((r) => r.language_code).filter((l): l is string => !!l))].sort(), [rows]);
  const current = rows.find((r) => r.name === selected) ?? filtered[0];
  const openDrafts = drafts.filter((d) => OPEN_DRAFT_STATUSES.includes(d.status)).length;
  const setFilter = (patch: Partial<TemplateFilters>) => setFilters((f) => ({ ...f, ...patch }));
  const filtering = filters.search !== '' || filters.status !== ALL_OPTION || filters.category !== ALL_OPTION || filters.language !== ALL_OPTION;

  if (unavailable) return <BridgeUnavailable />;

  if (view.kind !== 'browse') {
    return (
      <TemplateEditor
        mode={view.kind}
        gateway={gateway}
        detail={view.kind === 'edit' ? view.detail : undefined}
        isAdmin={isAdmin}
        onCancel={() => setView({ kind: 'browse' })}
        onSaved={(result) => {
          setView({ kind: 'browse' });
          if (result.kind === 'draft') {
            setSection('drafts');
            void loadDrafts();
          } else {
            if (result.kind === 'submitted') setSelected(result.name);
            setSection('templates');
            setRefreshKey((k) => k + 1);
            void load();
          }
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      <Tabs value={section} onValueChange={setSection}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList>
            <TabsTrigger value="templates">Templates</TabsTrigger>
            <TabsTrigger value="drafts" className="gap-1.5">
              Drafts awaiting approval
              {openDrafts > 0 && <Badge variant="pill-warning" size="sm">{openDrafts}</Badge>}
            </TabsTrigger>
          </TabsList>
          <div className="flex flex-wrap items-center gap-2">
            <ManagerLink url={manager.url} businessId={manager.businessId} />
            <Button variant="outline" size="sm" onClick={sync} disabled={syncing || !gateway}>
              {syncing ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1.5 h-4 w-4" />}
              Sync
            </Button>
            <Button size="sm" onClick={() => setView({ kind: 'create' })}>
              <Plus className="mr-1.5 h-4 w-4" /> {isAdmin ? 'New template' : 'Request template'}
            </Button>
          </div>
        </div>
        {!gateway && <p className="pt-2 text-xs text-steel">Choose a WhatsApp gateway above to see and sync its templates.</p>}

        <TabsContent value="templates" className="pt-4">
          {error && <LoadError message={error} onRetry={load} />}
          {loading && rows.length === 0 ? (
            <div className="flex items-center gap-2 text-xs text-steel"><Loader2 className="h-4 w-4 animate-spin" /> Loading templates...</div>
          ) : rows.length === 0 && !error ? (
            <div className="space-y-3 rounded-sm border border-line p-8 text-center">
              <p className="text-sm font-medium text-ink">No templates yet</p>
              <p className="text-xs text-steel">Create your first message template, or sync the ones you already have in WhatsApp.</p>
              <Button size="sm" onClick={() => setView({ kind: 'create' })}>
                <Plus className="mr-1.5 h-4 w-4" /> {isAdmin ? 'New template' : 'Request template'}
              </Button>
            </div>
          ) : rows.length > 0 ? (
            <div className="grid gap-5 md:grid-cols-[340px_minmax(0,1fr)]">
              <div className="space-y-3">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-steel-soft" />
                  <Input
                    aria-label="Search templates" className="pl-8" placeholder="Search templates..."
                    value={filters.search} onChange={(e) => setFilter({ search: e.target.value })}
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <Select value={filters.status} onValueChange={(v) => setFilter({ status: v })}>
                    <SelectTrigger aria-label="Filter by status"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL_OPTION}>Any status</SelectItem>
                      {TEMPLATE_STATUSES.map((s) => <SelectItem key={s} value={s}>{statusInfo(s).label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Select value={filters.category} onValueChange={(v) => setFilter({ category: v })}>
                    <SelectTrigger aria-label="Filter by category"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL_OPTION}>Any category</SelectItem>
                      <SelectItem value="MARKETING">Marketing</SelectItem>
                      <SelectItem value="UTILITY">Utility</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={filters.language} onValueChange={(v) => setFilter({ language: v })}>
                    <SelectTrigger aria-label="Filter by language"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL_OPTION}>Any language</SelectItem>
                      {languages.map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                {filtered.length === 0 ? (
                  <p className="rounded-sm border border-line p-4 text-center text-xs text-steel">
                    No templates match{filtering ? ' these filters' : ''}.
                  </p>
                ) : (
                  <ul className="max-h-[calc(100vh-18rem)] divide-y divide-line overflow-y-auto rounded-sm border border-line">
                    {filtered.map((t) => {
                      const active = t.name === current?.name;
                      return (
                        <li key={t.name}>
                          <button
                            type="button" aria-current={active} onClick={() => setSelected(t.name)}
                            className={`block w-full space-y-1.5 border-l-2 px-3 py-2.5 text-left hover:bg-paper-deep ${active ? 'border-signal bg-paper-deep' : 'border-transparent'}`}
                          >
                            <span className="block truncate font-mono text-xs font-medium text-ink">{t.template_name || t.name}</span>
                            <span className="block text-[11px] text-steel">
                              {t.category === 'MARKETING' ? 'Marketing' : t.category === 'UTILITY' ? 'Utility' : t.category} · {t.language_code}
                            </span>
                            <span className="flex flex-wrap gap-1">
                              <StatusBadge status={t.status} />
                              <QualityBadge score={t.quality_score} />
                              <CategoryChangeBadge pending={t.category_change_pending} to={t.correct_category} />
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
              <div className="min-w-0 rounded-sm border border-line p-4">
                {current ? (
                  <TemplateDetailPane
                    row={current}
                    refreshKey={refreshKey}
                    onSend={setToSend}
                    onEdit={(detail) => setView({ kind: 'edit', detail })}
                    onDelete={setToDelete}
                    onUnavailable={() => setUnavailable(true)}
                  />
                ) : (
                  <p className="py-10 text-center text-xs text-steel">Select a template to see its preview and status.</p>
                )}
              </div>
            </div>
          ) : null}
        </TabsContent>

        <TabsContent value="drafts" className="pt-4">
          <DraftsPanel
            drafts={drafts}
            isAdmin={isAdmin}
            onChanged={() => { void loadDrafts(); void load(); }}
            onUnavailable={() => setUnavailable(true)}
          />
        </TabsContent>
      </Tabs>

      <SendTemplateDialog template={toSend} onClose={() => setToSend(null)} gateway={gateway} />

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete template?</AlertDialogTitle>
            <AlertDialogDescription>
              {toDelete?.template_name} will be removed. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
