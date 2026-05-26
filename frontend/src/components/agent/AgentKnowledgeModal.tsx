import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Combobox } from '@/components/ui/combobox';
import { knowledgeModes } from '@/data/knowledge';
import { getKnowledgeSources } from '@/services/knowledgeApi';
import type { AgentKnowledgeRow } from '@/types/agent.types';
import type { ComboboxOption } from '@/components/ui/combobox';

interface AgentKnowledgeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (row: AgentKnowledgeRow) => void;
  initialData?: AgentKnowledgeRow | null;
}

export function AgentKnowledgeModal({
  open,
  onOpenChange,
  onSave,
  initialData,
}: AgentKnowledgeModalProps) {
  const [knowledgeSource, setKnowledgeSource] = useState('');
  const [mode, setMode] = useState<'Mandatory' | 'Optional'>('Optional');
  const [priority, setPriority] = useState(0);
  const [maxChunks, setMaxChunks] = useState(5);
  const [tokenBudget, setTokenBudget] = useState(2000);
  const [description, setDescription] = useState('');
  const [sourceOptions, setSourceOptions] = useState<ComboboxOption[]>([]);

  useEffect(() => {
    if (!open) return;

    getKnowledgeSources({ limit: 500 }).then((res) => {
      const opts = res.items.map((s) => ({
        value: s.name,
        label: s.source_name || s.name,
      }));
      setSourceOptions(opts);
    });
  }, [open]);

  useEffect(() => {
    if (open && initialData) {
      setKnowledgeSource(initialData.knowledge_source);
      setMode(initialData.mode);
      setPriority(initialData.priority);
      setMaxChunks(initialData.max_chunks);
      setTokenBudget(initialData.token_budget);
      setDescription(initialData.description || '');
    } else if (open) {
      setKnowledgeSource('');
      setMode('Optional');
      setPriority(0);
      setMaxChunks(5);
      setTokenBudget(2000);
      setDescription('');
    }
  }, [open, initialData]);

  const isValid = useMemo(() => !!knowledgeSource, [knowledgeSource]);

  const handleSave = () => {
    if (!isValid) return;
    onSave({
      ...(initialData?.name ? { name: initialData.name } : {}),
      knowledge_source: knowledgeSource,
      mode,
      priority,
      max_chunks: maxChunks,
      token_budget: tokenBudget,
      description: description || undefined,
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{initialData ? 'Edit Knowledge Link' : 'Add Knowledge Source'}</DialogTitle>
          <DialogDescription>
            Link a knowledge source to this agent for RAG-based retrieval.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>Knowledge Source *</Label>
            <Combobox
              options={sourceOptions}
              value={knowledgeSource}
              onValueChange={setKnowledgeSource}
              placeholder="Select knowledge source..."
              searchPlaceholder="Search knowledge sources..."
              emptyText="No knowledge sources found."
            />
          </div>

          <div className="space-y-2">
            <Label>Mode *</Label>
            <Select value={mode} onValueChange={(v) => setMode(v as 'Mandatory' | 'Optional')}>
              <SelectTrigger>
                <SelectValue placeholder="Select mode" />
              </SelectTrigger>
              <SelectContent>
                {knowledgeModes.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Mandatory: context injected into every prompt. Optional: agent queries via search tool.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <Label>Priority</Label>
              <Input
                type="number"
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
                min={0}
              />
            </div>
            <div className="space-y-2">
              <Label>Max Chunks</Label>
              <Input
                type="number"
                value={maxChunks}
                onChange={(e) => setMaxChunks(Number(e.target.value))}
                min={1}
              />
            </div>
            <div className="space-y-2">
              <Label>Token Budget</Label>
              <Input
                type="number"
                value={tokenBudget}
                onChange={(e) => setTokenBudget(Number(e.target.value))}
                min={0}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Description</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description for this knowledge link"
              rows={2}
            />
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSave} disabled={!isValid}>
            {initialData ? 'Update' : 'Add'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
