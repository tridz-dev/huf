import { useState, useEffect } from 'react';
import { ChevronDown, Loader2 } from 'lucide-react';
import { Dialog, DialogDescription, DialogTitle } from '../ui/dialog';
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
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '../ui/collapsible';
import { humanizeFlowError } from '@/lib/flow-graph/flowValidation';
import { useFlowContext } from '../../contexts/FlowContext';
import { toast } from '@/lib/toast';
import { useNavigate } from 'react-router-dom';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { FlowSettingsReadOnly } from './FlowSettingsReadOnly';
import { getFlowConversionStatus, updateFlowAutoConvert } from '../../services/flowApi';
import { listFlowCategories } from '../../services/flow/flowCardsApi';
import { DELETE_FLOW_BUTTON, DELETE_FLOW_TITLE, deleteFlowMessage } from '../flow/list/DeleteFlowDialog';

interface FlowSettingsModalProps {
  open: boolean;
  onClose: () => void;
}

const NEW_CATEGORY = '__new__';
const BASE_CATEGORIES = ['Automation', 'Integration', 'Support', 'Sales'];
const NAME_LIMIT = 140;

/**
 * Flow settings: the basics (name, description, category), a collapsed "More" for the rarely needed procedure
 * option, and a separate "Danger zone". Deleting asks inside this same dialog (no second dialog on top). Saving
 * only changes these details: it never saves the steps, so unfinished edits on the canvas cannot make it fail.
 */
export function FlowSettingsModal({ open, onClose }: FlowSettingsModalProps) {
  const { activeFlow, updateFlowMetadata, deleteFlow } = useFlowContext();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [newCategory, setNewCategory] = useState('');
  const [usedCategories, setUsedCategories] = useState<string[]>([]);
  const [autoConvertToProcedure, setAutoConvertToProcedure] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { canManage } = useFlowPermissions();

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
    setNewCategory('');
    setError(null);
    setNameError(null);
    setConfirmingDelete(false);
    setMoreOpen(false);
  }

  useEffect(() => {
    if (!activeFlow || !open || !canManage) return;
    getFlowConversionStatus(activeFlow.id)
      .then((status) => setAutoConvertToProcedure(status.auto_convert_to_procedure))
      .catch(() => setAutoConvertToProcedure(false));
    void listFlowCategories().then(setUsedCategories);
    // Only when the dialog opens or another flow is shown (not on every background refresh of the flow).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFlow?.id, open]);

  const isLive = activeFlow?.status === 'active';
  // The details are filled in once the flow has loaded; until then the fields wait, so anything typed early is never replaced.
  const waiting = !activeFlow;

  const handleDelete = async () => {
    if (!activeFlow) return;
    setIsDeleting(true);
    try {
      await deleteFlow(activeFlow.id);
      toast.success('Flow deleted');
      setConfirmingDelete(false);
      onClose();
      navigate('/flows');
    } catch (err) {
      setError(humanizeFlowError(err, 'The flow could not be deleted. Try again.'));
      setConfirmingDelete(false);
    } finally {
      setIsDeleting(false);
    }
  };

  const chosenCategory = category === NEW_CATEGORY ? newCategory.trim() : category;

  const handleSave = async () => {
    if (!activeFlow) {
      setError('The flow is still loading. Try again in a moment.');
      return;
    }
    if (!name.trim()) {
      setNameError('Flow name is required');
      return;
    }
    setNameError(null);
    setError(null);

    setIsSaving(true);
    try {
      await updateFlowMetadata(activeFlow.id, { name: name.trim(), description, category: chosenCategory || 'Uncategorized' });
      await updateFlowAutoConvert(activeFlow.id, autoConvertToProcedure);
      toast.success('Flow settings updated');
      onClose();

      // Same best-effort note as the canvas Save button: the checkbox may have just changed, so say what happened.
      try {
        const conversion = await getFlowConversionStatus(activeFlow.id);
        if (conversion.conversion_note) {
          if (conversion.converted_procedure) toast.success(conversion.conversion_note);
          else toast.info(conversion.conversion_note);
        }
      } catch (conversionErr) {
        console.error('Failed to fetch flow conversion status:', conversionErr);
      }
    } catch (err) {
      // The dialog stays open with what was typed, and says what went wrong in plain words.
      const message = humanizeFlowError(err, 'The settings could not be saved. Try again.');
      setError(message);
      toast.error('Could not update the settings', { description: message });
    } finally {
      setIsSaving(false);
    }
  };

  if (!canManage) {
    return <FlowSettingsReadOnly open={open} onClose={onClose} name={name} description={description} category={category} />;
  }

  const categories = [...new Set([...BASE_CATEGORIES, ...usedCategories, ...(category && category !== NEW_CATEGORY ? [category] : [])])]
    .filter((c) => c.toLowerCase() !== 'uncategorized')
    .sort((a, b) => a.localeCompare(b));
  const busy = isSaving || isDeleting;

  return (
    <Dialog open={open} onOpenChange={(next) => !next && !busy && onClose()}>
      <DialogScrollContent className="sm:max-w-[460px]" data-testid="flow-settings-modal">
        {confirmingDelete ? (
          <>
            <DialogScrollHeader>
              <DialogTitle data-testid="flow-settings-delete-title">{DELETE_FLOW_TITLE}</DialogTitle>
              <DialogDescription asChild>
                <div>
                  <span className="mb-2 block break-words font-medium text-foreground" title={activeFlow?.name} data-testid="flow-delete-name">
                    {activeFlow?.name}
                  </span>
                  {deleteFlowMessage(isLive)}
                </div>
              </DialogDescription>
            </DialogScrollHeader>
            <DialogScrollBody className="py-2" />
            <DialogScrollFooter className="justify-end">
              <Button variant="outline" size="sm" data-testid="flow-settings-delete-cancel" onClick={() => setConfirmingDelete(false)} disabled={isDeleting}>
                Cancel
              </Button>
              <Button variant="destructive" size="sm" className="gap-2" data-testid="flow-settings-delete-confirm" onClick={() => void handleDelete()} disabled={isDeleting}>
                {isDeleting && <Loader2 className="h-4 w-4 animate-spin" />}
                {DELETE_FLOW_BUTTON}
              </Button>
            </DialogScrollFooter>
          </>
        ) : (
          <>
            <DialogScrollHeader>
              <DialogTitle>Flow settings</DialogTitle>
              <DialogDescription>Help teammates find this flow and know what it does.</DialogDescription>
            </DialogScrollHeader>
            <DialogScrollBody className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="name">Flow name</Label>
                <Input
                  id="name"
                  data-testid="flow-settings-name"
                  value={name}
                  disabled={waiting}
                  maxLength={NAME_LIMIT}
                  aria-invalid={!!nameError}
                  onChange={(e) => {
                    setName(e.target.value);
                    if (nameError) setNameError(null);
                  }}
                  placeholder="For example: New order alert"
                />
                {nameError ? (
                  <p role="alert" className="text-meta text-destructive" data-testid="flow-settings-name-error">{nameError}</p>
                ) : (
                  <p className="text-meta text-muted-foreground" data-testid="flow-settings-name-hint">
                    Pick a name that says what the flow does. It is required.
                  </p>
                )}
              </div>
              <div className="grid gap-2">
                <Label htmlFor="description">Description (optional)</Label>
                <Textarea
                  id="description"
                  data-testid="flow-settings-description"
                  className="min-h-[80px]"
                  value={description}
                  disabled={waiting}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="For example: Sends a Slack message when a large order comes in."
                />
                <p className="text-meta text-muted-foreground" data-testid="flow-settings-description-hint">
                  Shown on the flow's card. Helpful for teammates who did not build it.
                </p>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="category">Category</Label>
                <Select value={category || 'Uncategorized'} onValueChange={setCategory} disabled={waiting}>
                  <SelectTrigger id="category" data-testid="flow-settings-category">
                    <SelectValue placeholder="Select category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Uncategorized">Uncategorized</SelectItem>
                    {categories.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                    <SelectItem value={NEW_CATEGORY}>New category...</SelectItem>
                  </SelectContent>
                </Select>
                {category === NEW_CATEGORY && (
                  <Input
                    aria-label="New category name"
                    data-testid="flow-settings-category-new"
                    value={newCategory}
                    maxLength={60}
                    onChange={(e) => setNewCategory(e.target.value)}
                    placeholder="For example: Finance"
                    autoFocus
                  />
                )}
                <p className="text-meta text-muted-foreground" data-testid="flow-settings-category-hint">
                  Groups flows in the list so you can filter by it.
                </p>
              </div>

              <Collapsible open={moreOpen} onOpenChange={setMoreOpen}>
                <CollapsibleTrigger asChild>
                  <button
                    type="button"
                    className="flex items-center gap-1 text-sm font-medium text-steel hover:text-ink"
                    data-testid="flow-settings-more"
                  >
                    <ChevronDown className={`h-4 w-4 transition-transform ${moreOpen ? '' : '-rotate-90'}`} aria-hidden />
                    More
                  </button>
                </CollapsibleTrigger>
                <CollapsibleContent className="pt-3">
                  <div className="flex flex-row items-start gap-2">
                    <Checkbox
                      id="auto-convert-to-procedure"
                      data-testid="flow-settings-auto-convert"
                      checked={autoConvertToProcedure}
                      onCheckedChange={(checked) => setAutoConvertToProcedure(checked === true)}
                      className="mt-0.5"
                    />
                    <div className="grid gap-1 leading-snug">
                      <Label htmlFor="auto-convert-to-procedure" className="font-medium">
                        Keep a reusable procedure up to date
                      </Label>
                      <p className="text-sm text-muted-foreground">
                        Every save refreshes a draft procedure made from this flow. It only works for flows without AI
                        steps (agents, AI choices) or approvals.
                      </p>
                    </div>
                  </div>
                </CollapsibleContent>
              </Collapsible>

              <section className="grid gap-2 rounded-lg border border-destructive/30 p-3" aria-labelledby="flow-danger-title" data-testid="flow-settings-danger-zone">
                <h3 id="flow-danger-title" className="text-sm font-semibold text-destructive">Danger zone</h3>
                <p className="text-sm text-muted-foreground">
                  {isLive ? 'This flow is live. ' : ''}Deleting removes the flow and its run history for good.
                </p>
                <div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="border-destructive/40 text-destructive hover:text-destructive"
                    data-testid="flow-settings-delete"
                    onClick={() => setConfirmingDelete(true)}
                    disabled={busy || !activeFlow}
                  >
                    Delete flow
                  </Button>
                </div>
              </section>

              {error && (
                <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" data-testid="flow-settings-error">
                  {error}
                </p>
              )}
            </DialogScrollBody>
            <DialogScrollFooter className="justify-end">
              <Button variant="outline" size="sm" data-testid="flow-settings-cancel" onClick={onClose} disabled={busy}>
                Cancel
              </Button>
              <Button size="sm" data-testid="flow-settings-save" onClick={() => void handleSave()} disabled={busy || !activeFlow} className="gap-2">
                {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
                Save changes
              </Button>
            </DialogScrollFooter>
          </>
        )}
      </DialogScrollContent>
    </Dialog>
  );
}
