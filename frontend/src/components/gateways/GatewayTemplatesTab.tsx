import { useEffect, useMemo, useState } from 'react';
import { type ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import { Plus, Trash2, Upload, RefreshCw, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { DataListView } from '@/components/dashboard/DataListView';
import { EmptyState } from '@/components/dashboard';
import {
  listGatewayTemplates,
  pushGatewayTemplate,
  syncGatewayTemplate,
  deleteGatewayTemplate,
  createGatewayTemplate,
  type GatewayTemplate,
} from '@/services/gatewayTemplateApi';
import { cn } from '@/lib/utils';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

interface GatewayTemplatesTabProps {
  gatewayName: string;
}

type TemplateFormMode = 'create' | 'edit' | null;

export function GatewayTemplatesTab({ gatewayName }: GatewayTemplatesTabProps) {
  const [templates, setTemplates] = useState<GatewayTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [formMode, setFormMode] = useState<TemplateFormMode>(null);
  const [formData, setFormData] = useState<Partial<GatewayTemplate>>({});
  const [saving, setSaving] = useState(false);
  const [actioningName, setActioningName] = useState<string | null>(null);
  const [deleteConfirmName, setDeleteConfirmName] = useState<string | null>(null);
  const [deletingTemplate, setDeletingTemplate] = useState(false);

  useEffect(() => {
    loadTemplates();
  }, [gatewayName]);

  async function loadTemplates() {
    setLoading(true);
    try {
      const list = await listGatewayTemplates(gatewayName);
      setTemplates(list);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not load templates.');
    } finally {
      setLoading(false);
    }
  }

  function openCreateForm() {
    setFormMode('create');
    setFormData({
      gateway: gatewayName,
      template_type: 'TEXT',
      language: 'en_US',
      category: 'MARKETING',
      status: 'PENDING_REVIEW',
      components: '[]',
    });
  }

  async function handleSaveTemplate() {
    if (!formData.template_name?.trim()) {
      toast.error('Template name is required');
      return;
    }

    setSaving(true);
    try {
      const created = await createGatewayTemplate(formData);
      setTemplates((prev) => [created, ...prev]);
      toast.success('Template created');
      closeForm();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save template');
    } finally {
      setSaving(false);
    }
  }

  function closeForm() {
    setFormMode(null);
    setFormData({});
  }

  async function handlePush(template: GatewayTemplate) {
    setActioningName(template.name);
    try {
      const updated = await pushGatewayTemplate(template.name);
      setTemplates((prev) => prev.map((t) => (t.name === updated.name ? updated : t)));
      toast.success(`Template pushed: ${updated.external_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to push template');
    } finally {
      setActioningName(null);
    }
  }

  async function handleSync(template: GatewayTemplate) {
    setActioningName(template.name);
    try {
      const updated = await syncGatewayTemplate(template.name);
      setTemplates((prev) => prev.map((t) => (t.name === updated.name ? updated : t)));
      toast.success('Template status synced');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to sync template');
    } finally {
      setActioningName(null);
    }
  }

  async function handleDelete(name: string) {
    setDeletingTemplate(true);
    try {
      await deleteGatewayTemplate(name);
      setTemplates((prev) => prev.filter((t) => t.name !== name));
      toast.success('Template deleted');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete template');
    } finally {
      setDeletingTemplate(false);
      setDeleteConfirmName(null);
    }
  }

  const columns = useMemo<ColumnDef<GatewayTemplate>[]>(
    () => [
      {
        accessorKey: 'template_name',
        header: 'Template Name',
        cell: ({ row }) => <span className="text-sm font-medium text-ink">{row.original.template_name}</span>,
      },
      {
        accessorKey: 'category',
        header: 'Category',
        cell: ({ row }) => <span className="text-xs text-steel">{row.original.category}</span>,
      },
      {
        accessorKey: 'language',
        header: 'Language',
        cell: ({ row }) => <span className="text-xs font-mono text-steel">{row.original.language}</span>,
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => (
          <span
            className={cn('text-xs font-medium', {
              'text-good': row.original.status === 'APPROVED',
              'text-warning': row.original.status === 'PENDING_REVIEW',
              'text-destructive': row.original.status === 'REJECTED',
            })}
          >
            {row.original.status}
          </span>
        ),
      },
      {
        id: 'actions',
        header: '',
        cell: ({ row }) => {
          const template = row.original;
          const busy = actioningName === template.name || deletingTemplate;
          return (
            <div className="flex items-center justify-end gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-7 px-2.5 text-xs"
                disabled={busy}
                onClick={() => handlePush(template)}
              >
                <Upload className="mr-1 h-3.5 w-3.5" /> Push
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 px-2.5 text-xs"
                disabled={busy}
                onClick={() => handleSync(template)}
              >
                <RefreshCw className="mr-1 h-3.5 w-3.5" /> Sync
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2.5 text-xs text-destructive hover:text-destructive"
                disabled={busy}
                onClick={() => setDeleteConfirmName(template.name)}
              >
                <Trash2 className="mr-1 h-3.5 w-3.5" /> Delete
              </Button>
            </div>
          );
        },
      },
    ],
    [actioningName, deletingTemplate]
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium text-ink">Gateway Templates</p>
          <p className="text-[11px] text-steel">Manage WhatsApp message templates for this gateway</p>
        </div>
        <Button size="sm" onClick={openCreateForm} className="h-9 text-xs">
          <Plus className="mr-1.5 h-4 w-4" /> New Template
        </Button>
      </div>

      <DataListView
        columns={columns}
        data={templates}
        loading={loading}
        emptyState={
          <EmptyState
            variant="passive"
            icon={Plus}
            title="No templates yet"
            description="Create a gateway template to send formatted messages through WhatsApp."
          />
        }
      />

      {formMode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl border border-line bg-panel p-6 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-line pb-4">
              <h3 className="text-base font-semibold text-ink">New Template</h3>
              <Button
                variant="ghost"
                size="icon"
                onClick={closeForm}
                className="h-auto w-auto rounded-lg p-1.5 text-steel hover:bg-paper hover:text-ink"
              >
                <X className="h-5 w-5" />
              </Button>
            </div>

            <div className="space-y-3">
              <label className="grid gap-1 text-xs font-medium text-ink">
                Template name<span className="text-destructive"> *</span>
                <Input
                  className="h-9 text-xs"
                  value={formData.template_name || ''}
                  onChange={(e) => setFormData({ ...formData, template_name: e.target.value })}
                  placeholder="e.g. order_confirmation"
                  disabled={formMode === 'edit'}
                />
              </label>

              <label className="grid gap-1 text-xs font-medium text-ink">
                Template type
                <Input
                  className="h-9 text-xs"
                  value={formData.template_type || 'TEXT'}
                  onChange={(e) => setFormData({ ...formData, template_type: e.target.value })}
                />
              </label>

              <label className="grid gap-1 text-xs font-medium text-ink">
                Category
                <Input
                  className="h-9 text-xs"
                  value={formData.category || 'MARKETING'}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                />
              </label>

              <label className="grid gap-1 text-xs font-medium text-ink">
                Language code
                <Input
                  className="h-9 text-xs"
                  value={formData.language || 'en_US'}
                  onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                  placeholder="e.g. en_US, fr_FR"
                />
              </label>

              <label className="grid gap-1 text-xs font-medium text-ink">
                Components (JSON)
                <textarea
                  className="min-h-[200px] rounded-md border border-line bg-background p-2 text-xs font-mono text-ink focus:outline-none focus:ring-2 focus:ring-primary"
                  value={formData.components || '[]'}
                  onChange={(e) => setFormData({ ...formData, components: e.target.value })}
                  placeholder='[{"type": "BODY", "text": "Hello {{1}}, your order is ready"}]'
                />
                <span className="text-[11px] font-normal text-steel">
                  JSON array of component objects (HEADER, BODY, FOOTER, BUTTONS)
                </span>
              </label>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-line pt-4">
              <Button variant="outline" size="sm" className="h-9 text-xs" onClick={closeForm} disabled={saving}>
                Cancel
              </Button>
              <Button size="sm" className="h-9 text-xs" disabled={saving} onClick={handleSaveTemplate}>
                {saving ? 'Saving...' : 'Save Template'}
              </Button>
            </div>
          </div>
        </div>
      )}

      <AlertDialog open={Boolean(deleteConfirmName)} onOpenChange={(open) => !open && setDeleteConfirmName(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this template?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes the template &quot;{deleteConfirmName}&quot; from this gateway.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletingTemplate}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteConfirmName && handleDelete(deleteConfirmName)}
              disabled={deletingTemplate}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deletingTemplate ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
