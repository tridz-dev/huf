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
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={isSaving || !activeFlow}>
            {isSaving ? 'Saving...' : 'Save Settings'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
