import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogDescription,
  DialogTitle,
} from '../ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '../ui/dialog-scroll';
import { Input } from '../ui/input';
import { Textarea } from '../ui/textarea';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Checkbox } from '../ui/checkbox';
import { humanizeFlowError } from '@/lib/flowValidation';
import { useFlowContext } from '../../contexts/FlowContext';
import { toast } from '@/lib/toast';
import { useNavigate } from 'react-router-dom';
import { useFlowPermissions } from '@/hooks/useFlowPermissions';
import { DisabledReason } from '../flow/DisabledReason';
import { Trash2, Loader2, AlertTriangle } from 'lucide-react';
import { getFlowConversionStatus, updateFlowAutoConvert } from '../../services/flowApi';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../ui/alert-dialog';

interface FlowSettingsModalProps {
  open: boolean;
  onClose: () => void;
}

export function FlowSettingsModal({ open, onClose }: FlowSettingsModalProps) {
  const { activeFlow, updateFlowMetadata } = useFlowContext();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [autoConvertToProcedure, setAutoConvertToProcedure] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const navigate = useNavigate();
  const { canManage, readOnlyReason } = useFlowPermissions();

  // Fill the fields while rendering, once per opening: the first thing the user sees (and can edit) is already the
  // flow's real values, so a late effect can never put them back over what was typed or cleared.
  const [filledFor, setFilledFor] = useState<string | null>(null);
  if (!open && filledFor !== null) {
    setFilledFor(null);
  } else if (open && activeFlow && filledFor !== activeFlow.id) {
    setFilledFor(activeFlow.id);
    setName(activeFlow.name || '');
    setDescription(activeFlow.description || '');
    setCategory(activeFlow.category || '');
  }

  useEffect(() => {
    if (!activeFlow || !open) return;
    getFlowConversionStatus(activeFlow.id)
      .then((status) => setAutoConvertToProcedure(status.auto_convert_to_procedure))
      .catch(() => setAutoConvertToProcedure(false));
    // Only when the dialog opens or another flow is shown (not on every background refresh of the flow).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFlow?.id, open]);

  const { deleteFlow } = useFlowContext();

  const handleDelete = async () => {
    if (!activeFlow) return;

    setIsDeleting(true);
    try {
      await deleteFlow(activeFlow.id);
      toast.success('Flow deleted successfully');
      // Reset dialog states before closing to ensure AlertDialog unmounts cleanly
      // This is critical when already on /flows, since navigate('/flows') won't remount
      setShowDeleteConfirm(false);
      setIsDeleting(false);
      onClose();
      navigate('/flows');
    } catch (err) {
      toast.error('Failed to delete flow', {
        description: err instanceof Error && err.message ? err.message : 'Unknown error'
      });
      setIsDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const handleSave = async () => {
    if (!activeFlow) {
      toast.error('Flow is still loading');
      return;
    }
    if (!name.trim()) {
      toast.error('Flow name is required');
      return;
    }

    setIsSaving(true);
    try {
      await updateFlowMetadata(activeFlow.id, {
        name,
        description,
        category,
      });
      await updateFlowAutoConvert(activeFlow.id, autoConvertToProcedure);
      toast.success('Flow settings updated');
      onClose();

      // Same best-effort note as the canvas Save button -- the checkbox above just
      // changed, so tell the user what the backend did about it.
      try {
        const conversion = await getFlowConversionStatus(activeFlow.id);
        if (conversion.conversion_note) {
          if (conversion.converted_procedure) {
            toast.success(conversion.conversion_note);
          } else {
            toast.info(conversion.conversion_note);
          }
        }
      } catch (conversionErr) {
        console.error('Failed to fetch flow conversion status:', conversionErr);
      }
    } catch (err) {
      toast.error('Could not update the settings', { description: humanizeFlowError(err) });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogScrollContent className="sm:max-w-[425px]" data-testid="flow-settings-modal">
        <DialogScrollHeader>
          <DialogTitle>Flow settings</DialogTitle>
          <DialogDescription>The name, description and category show up in the flows list.</DialogDescription>
        </DialogScrollHeader>
        <DialogScrollBody className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="name">Flow name</Label>
            <Input
              id="name"
              data-testid="flow-settings-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="For example: New order alert"
            />
            <p className="text-micro text-muted-foreground" data-testid="flow-settings-name-hint">Pick a name that says what the flow does. It is required.</p>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="description">Description (optional)</Label>
            <Textarea
              id="description"
              data-testid="flow-settings-description"
              className="min-h-[80px]"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="For example: Sends a Slack message when a large order comes in."
            />
            <p className="text-micro text-muted-foreground" data-testid="flow-settings-description-hint">Shown on the flow's card. Helpful for teammates who did not build it.</p>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="category">Category</Label>
            <Select value={category || 'Uncategorized'} onValueChange={setCategory}>
              <SelectTrigger id="category" data-testid="flow-settings-category">
                <SelectValue placeholder="Select category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Uncategorized">Uncategorized</SelectItem>
                <SelectItem value="Automation">Automation</SelectItem>
                <SelectItem value="Integration">Integration</SelectItem>
                <SelectItem value="Support">Support</SelectItem>
                <SelectItem value="Sales">Sales</SelectItem>
                <SelectItem value="Huf Demo">Huf Demo</SelectItem>
                {category && !['Uncategorized', 'Automation', 'Integration', 'Support', 'Sales', 'Huf Demo'].includes(category) && (
                  <SelectItem value={category}>{category}</SelectItem>
                )}
              </SelectContent>
            </Select>
            <p className="text-micro text-muted-foreground" data-testid="flow-settings-category-hint">Groups flows in the list so you can filter by it.</p>
          </div>
          <div className="flex flex-row items-start gap-2">
            <Checkbox
              id="auto-convert-to-procedure"
              data-testid="flow-settings-auto-convert"
              checked={autoConvertToProcedure}
              onCheckedChange={(checked) => setAutoConvertToProcedure(checked === true)}
              className="mt-0.5"
            />
            <div className="grid gap-1 leading-none">
              <Label htmlFor="auto-convert-to-procedure" className="font-normal">
                Create a procedure from this flow on save
              </Label>
              <p className="text-sm text-muted-foreground">
                Every save turns this flow into a draft, reusable procedure. This only works for flows
                without AI-driven steps (agent runs, LLM routers or approvals).
              </p>
            </div>
          </div>
        </DialogScrollBody>
        <DialogScrollFooter className="items-center justify-between sm:justify-between">
          {canManage ? (
            <Button
              variant="destructive-ghost"
              size="sm"
              className="gap-2"
              data-testid="flow-settings-delete"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={isDeleting || isSaving}
            >
              {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
              Delete flow
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="outline" size="sm" data-testid="flow-settings-cancel" onClick={onClose} disabled={isDeleting || isSaving}>
              Cancel
            </Button>
            <DisabledReason reason={canManage ? null : readOnlyReason}>
              <Button size="sm" data-testid="flow-settings-save" onClick={handleSave} disabled={isSaving || isDeleting || !activeFlow || !canManage} className="gap-2">
                {isSaving && <Loader2 className="w-4 h-4 animate-spin" />}
                Save changes
              </Button>
            </DisabledReason>
          </div>
        </DialogScrollFooter>
      </DialogScrollContent>

      <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-destructive" />
              Are you absolutely sure?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete the flow
              <span className="font-semibold text-foreground px-1">"{activeFlow?.name}"</span>
              and all of its associated run history.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                handleDelete();
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={isDeleting}
            >
              {isDeleting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete Flow'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}
