import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { useFlowContext } from '../../contexts/FlowContext';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { Trash2, Loader2, AlertTriangle } from 'lucide-react';
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
  const [maxHops, setMaxHops] = useState(100);
  const [mode, setMode] = useState<'normal' | 'agentic'>('normal');
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (activeFlow && open) {
      setName(activeFlow.name || '');
      setDescription(activeFlow.description || '');
      setCategory(activeFlow.category || '');
      const settings = activeFlow.settings || {};
      setMode((settings.mode as 'normal' | 'agentic') || 'normal');
      setMaxHops(typeof settings.max_hops === 'number' ? settings.max_hops : 100);
    }
  }, [activeFlow, open]);

  const { deleteFlow } = useFlowContext();

  const handleDelete = async () => {
    if (!activeFlow) return;

    setIsDeleting(true);
    try {
      await deleteFlow(activeFlow.id);
      toast.success('Flow deleted successfully');
      onClose();
      navigate('/flows');
    } catch (err: any) {
      toast.error('Failed to delete flow', {
        description: err.message || 'Unknown error'
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

    if (!Number.isFinite(maxHops) || maxHops < 1) {
      toast.error('Max Hops must be at least 1');
      return;
    }

    setIsSaving(true);
    try {
      await updateFlowMetadata(activeFlow.id, {
        name,
        description,
        category,
        settings: {
          ...(activeFlow.settings || {}),
          mode,
          max_hops: maxHops,
        },
      });
      toast.success('Flow settings updated');
      onClose();
    } catch (err) {
      toast.error('Failed to update settings', { description: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Flow Settings</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="name">Flow Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Enter flow name..."
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="description">Description (Optional)</Label>
            <textarea
              id="description"
              className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What does this flow do?"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="category">Category</Label>
            <Select value={category || 'Uncategorized'} onValueChange={setCategory}>
              <SelectTrigger id="category">
                <SelectValue placeholder="Select category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Uncategorized">Uncategorized</SelectItem>
                <SelectItem value="Automation">Automation</SelectItem>
                <SelectItem value="Integration">Integration</SelectItem>
                <SelectItem value="Support">Support</SelectItem>
                <SelectItem value="Sales">Sales</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="mode">Execution Mode</Label>
              <Select value={mode} onValueChange={(v: any) => setMode(v)}>
                <SelectTrigger id="mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="normal">Normal</SelectItem>
                  <SelectItem value="agentic">Agentic</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="max-hops">Max Hops</Label>
              <Input
                id="max-hops"
                type="number"
                value={maxHops}
                onChange={(e) => {
                  const raw = e.target.value;
                  const parsed = parseInt(raw, 10);
                  setMaxHops(Number.isFinite(parsed) ? parsed : 100);
                }}
                min={1}
                max={1000}
              />
            </div>
          </div>
        </div>
        <DialogFooter className="sm:justify-between items-center border-t pt-4 mt-2">
          <Button
            variant="outline"
            size="sm"
            className="text-destructive border-destructive/30 hover:bg-destructive/10 hover:text-destructive hover:border-destructive/50 gap-2"
            onClick={() => setShowDeleteConfirm(true)}
            disabled={isDeleting || isSaving}
          >
            {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
            Delete Flow
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onClose} disabled={isDeleting || isSaving}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave} disabled={isSaving || isDeleting || !activeFlow} className="gap-2">
              {isSaving && <Loader2 className="w-4 h-4 animate-spin" />}
              Save Changes
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>

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
