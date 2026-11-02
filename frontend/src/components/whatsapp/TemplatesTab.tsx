import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
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
  SharedTemplateError, type TemplateUser, deleteTemplate, errorText, getTemplate, isBridgeUnavailable, listTemplateDrafts, listTemplates, syncTemplates,
  type TemplateDetail, type TemplateDraft, type WhatsAppTemplate,
} from '@/services/whatsappApi';
import { BridgeUnavailable, LoadError } from './BridgeUnavailable';
import { CategoryChangeBadge, QualityBadge, SharedPill, StatusBadge, UsedByChips } from './TemplateBadges';
import { listSolutions } from '@/services/solutionsApi';
import type { SolutionSummary } from '@/types/solutions';
import { DraftsPanel } from './DraftsPanel';
import { ManagerLink } from './ManagerLink';
import { SendTemplateDialog } from './SendTemplateDialog';
import { localeLabel } from './template/locales';
import { SharedTemplateDialog } from './SharedTemplateDialog';
import { TemplateDetailPane } from './TemplateDetailPane';
import type { TemplateWizardDraft } from './template/draft';
import { fromTemplateDetail } from './template/payload';
import { TemplateWizard, type WizardResult } from './TemplateWizard';
import {
  ALL_OPTION, OPEN_DRAFT_STATUSES, TEMPLATE_STATUSES, categoryLabel, filterTemplates, isSharedTemplate, statusInfo, statusToastText, type TemplateFilters,
} from './templateModel';

const STATUS_EVENT = 'whatsapp_template_status';


interface TemplatesTabProps {
  gateway?: string;
  /** Show only this solution's templates and hide account-level actions (sync, manager link, drafts). */
  scopeSolution?: string;
  /** Route-driven selection (Channels shell): when `onSelect` is given, the selected template comes from the URL. */
  selectedName?: string;
  onSelect?: (name: string) => void;
}

export function TemplatesTab({ gateway, scopeSolution, selectedName, onSelect }: TemplatesTabProps) {
  const scoped = !!scopeSolution;
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
  // The wizard is addressed by the URL (?new=1 or ?edit=<name>) so it can be linked and survives a reload.
  const [params, setParams] = useSearchParams();
  const creating = params.get('new') === '1';
  const editName = params.get('edit') ?? '';
  const [editDetail, setEditDetail] = useState<TemplateDetail | null>(null);
  const [editAck, setEditAck] = useState(false);
  const [sharedConflict, setSharedConflict] = useState<TemplateUser[] | null>(null);
  const [copyDraft, setCopyDraft] = useState<TemplateWizardDraft | null>(null);
  const [editError, setEditError] = useState('');
  const [section, setSection] = useState('templates');
  const [selectedLocal, setSelectedLocal] = useState('');
  const selected = onSelect ? (selectedName ?? '') : selectedLocal;
  const setSelected = useCallback((name: string) => { if (onSelect) onSelect(name); else setSelectedLocal(name); }, [onSelect]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [filters, setFilters] = useState<TemplateFilters>({ search: '', status: ALL_OPTION, category: ALL_OPTION, language: ALL_OPTION, solution: ALL_OPTION });
  const [solutions, setSolutions] = useState<SolutionSummary[]>([]);
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
    const res = await listTemplates(gateway, undefined, scopeSolution);
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
  }, [gateway, scopeSolution]);

  useEffect(() => {
    if (scoped) return;
    let live = true;
    listSolutions().then((list) => { if (live) setSolutions(list); }).catch(() => { /* filter stays hidden */ });
    return () => { live = false; };
  }, [scoped]);

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

  const openWizard = useCallback((patch: { new?: string; edit?: string }) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete('new');
      next.delete('edit');
      for (const [k, v] of Object.entries(patch)) if (v) next.set(k, v);
      return next;
    });
  }, [setParams]);
  const closeWizard = useCallback(() => {
    setEditAck(false);
    setSharedConflict(null);
    setCopyDraft(null);
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete('new');
      next.delete('edit');
      return next;
    });
  }, [setParams]);

  // Fetch the template behind ?edit= (also gives the wizard its remaining edits).
  const loadEdit = useCallback(async () => {
    if (!editName) return;
    setEditError('');
    const res = await getTemplate(editName);
    if (res.success) setEditDetail(res);
    else if (isBridgeUnavailable(res)) setUnavailable(true);
    else setEditError(errorText(res));
  }, [editName]);
  useEffect(() => {
    if (editName && editDetail?.name !== editName) void loadEdit();
  }, [editName, editDetail, loadEdit]);

  const onWizardDone = (result: WizardResult) => {
    closeWizard();
    setEditDetail(null);
    if (result.kind === 'draft') {
      setSection('drafts');
      void loadDrafts();
    } else {
      setSelected(result.name);
      setSection('templates');
      setRefreshKey((k) => k + 1);
      void load();
    }
  };

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

  const runDelete = async (row: WhatsAppTemplate, acknowledgeShared?: boolean) => {
    let res;
    try {
      res = await deleteTemplate(row.name, acknowledgeShared);
    } catch (err) {
      if (err instanceof SharedTemplateError) {
        toast.error('This template is now shared with another solution. Open it again to review.');
        void load();
        return;
      }
      throw err;
    }
    if (res.success) {
      toast.success('Template deleted');
      setSelected('');
      void load();
    } else toast.error(errorText(res));
  };

  const confirmDelete = async () => {
    if (!toDelete) return;
    const row = toDelete;
    setToDelete(null);
    await runDelete(row);
  };

  const filtered = useMemo(() => filterTemplates(rows, filters), [rows, filters]);
  const languages = useMemo(() => [...new Set(rows.map((r) => r.language_code).filter((l): l is string => !!l))].sort(), [rows]);
  const current = rows.find((r) => r.name === selected) ?? filtered[0];
  const openDrafts = drafts.filter((d) => OPEN_DRAFT_STATUSES.includes(d.status)).length;
  const setFilter = (patch: Partial<TemplateFilters>) => setFilters((f) => ({ ...f, ...patch }));
  const filtering = filters.search !== '' || filters.status !== ALL_OPTION || filters.category !== ALL_OPTION || filters.language !== ALL_OPTION || (!!filters.solution && filters.solution !== ALL_OPTION);

  if (unavailable) return <BridgeUnavailable />;

  if (creating || editName) {
    const initial = editDetail?.name === editName ? editDetail : null;
    return (
      <div className="space-y-4">
        {creating ? (
          <TemplateWizard gatewayName={gateway ?? ''} isAdmin={isAdmin} copyFrom={copyDraft ?? undefined} onDone={onWizardDone} onCancel={closeWizard} />
        ) : initial ? (
          <TemplateWizard
            key={initial.name}
            gatewayName={gateway ?? ''}
            isAdmin={isAdmin}
            initial={fromTemplateDetail(initial)}
            docName={initial.name}
            editsLeft={initial.edits_left}
            acknowledgeShared={editAck}
            onSharedConflict={setSharedConflict}
            onDone={onWizardDone}
            onCancel={closeWizard}
          />
        ) : editError ? (
          <LoadError message={editError} onRetry={loadEdit} />
        ) : (
          <div className="flex items-center gap-2 text-xs text-steel"><Loader2 className="h-4 w-4 animate-spin" /> Loading template...</div>
        )}
        <SharedTemplateDialog
          open={sharedConflict !== null}
          action="edit"
          usedBy={sharedConflict ?? []}
          onConfirm={() => { setEditAck(true); setSharedConflict(null); }}
          onCopy={() => {
            const source = initial;
            setSharedConflict(null);
            if (!source) return;
            setEditAck(false);
            setCopyDraft(fromTemplateDetail(source));
            openWizard({ new: '1' });
          }}
          onCancel={() => setSharedConflict(null)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Tabs value={section} onValueChange={setSection}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList>
            <TabsTrigger value="templates">Templates</TabsTrigger>
            {!scoped && (
              <TabsTrigger value="drafts" className="gap-1.5">
                Drafts awaiting approval
                {openDrafts > 0 && <Badge variant="pill-warning" size="sm">{openDrafts}</Badge>}
              </TabsTrigger>
            )}
          </TabsList>
          <div className="flex flex-wrap items-center gap-2">
            {!scoped && <ManagerLink url={manager.url} businessId={manager.businessId} />}
            {!scoped && (
              <Button variant="outline" size="sm" onClick={sync} disabled={syncing || !gateway}>
                {syncing ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-1.5 h-4 w-4" />}
                Sync
              </Button>
            )}
            <Button size="sm" onClick={() => openWizard({ new: '1' })}>
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
              <Button size="sm" onClick={() => openWizard({ new: '1' })}>
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
                <div className="grid grid-cols-2 gap-2">
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
                  {!scoped && solutions.length > 0 && (
                    <Select value={filters.solution ?? ALL_OPTION} onValueChange={(v) => setFilter({ solution: v })}>
                      <SelectTrigger className="col-span-2" aria-label="Filter by solution"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ALL_OPTION}>Any solution</SelectItem>
                        {solutions.map((s) => <SelectItem key={s.name} value={s.name}>{s.title}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  )}
                  <Select value={filters.language} onValueChange={(v) => setFilter({ language: v })}>
                    <SelectTrigger className="col-span-2" aria-label="Filter by language"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL_OPTION}>Any language</SelectItem>
                      {languages.map((l) => <SelectItem key={l} value={l}>{localeLabel(l)}</SelectItem>)}
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
                              {categoryLabel(t.category)} · {localeLabel(t.language_code ?? '')}
                            </span>
                            <span className="flex flex-wrap gap-1">
                              <StatusBadge status={t.status} />
                              <QualityBadge score={t.quality_score} />
                              <CategoryChangeBadge pending={t.category_change_pending} to={t.correct_category} />
                              <SharedPill shared={isSharedTemplate(t)} />
                            </span>
                            <UsedByChips users={t.used_by} />
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
                    onEdit={(detail, ack) => { setEditDetail(detail); setEditAck(!!ack); openWizard({ edit: detail.name }); }}
                    onDelete={(r, ack) => (ack ? void runDelete(r, true) : setToDelete(r))}
                    onCopy={(d) => {
                      setCopyDraft(fromTemplateDetail(d));
                      openWizard({ new: '1' });
                    }}
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
