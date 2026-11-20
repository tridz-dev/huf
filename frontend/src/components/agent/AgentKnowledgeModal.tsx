import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { toast } from 'sonner';
import { KnowledgeSourcePicker } from './knowledge/KnowledgeSourcePicker';
import { KnowledgeAdvancedFields } from './knowledge/KnowledgeAdvancedFields';
import { useAttachableSources } from './knowledge/useAttachableSources';
import { knowledgeModes } from '@/data/knowledge';
import type { AgentKnowledgeRow } from '@/types/agent.types';

interface AgentKnowledgeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (row: AgentKnowledgeRow) => void;
  initialData?: AgentKnowledgeRow | null;
  onCreateNew?: () => void;
}

export function AgentKnowledgeModal({
  open,
  onOpenChange,
  onSave,
  initialData,
  onCreateNew,
}: AgentKnowledgeModalProps) {
  const [knowledgeSource, setKnowledgeSource] = useState('');
  const [mode, setMode] = useState<'Mandatory' | 'Optional'>('Optional');
  const [priority, setPriority] = useState(0);
  const [maxChunks, setMaxChunks] = useState(5);
  const [tokenBudget, setTokenBudget] = useState(2000);
  const [description, setDescription] = useState('');
  const { sources, loading } = useAttachableSources(open);

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
    toast.success(initialData ? 'Knowledge link updated. Click Save on the agent to keep it.' : 'Knowledge source added. Click Save on the agent to link it permanently.');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogScrollContent className="sm:max-w-lg">
        <DialogScrollHeader>
          <DialogTitle>{initialData ? 'Edit Knowledge Link' : 'Add Knowledge Source'}</DialogTitle>
          <DialogDescription>
            Choose a source this agent can answer from.
          </DialogDescription>
        </DialogScrollHeader>

        <DialogScrollBody className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>Knowledge source *</Label>
            {!loading && sources.length === 0 ? (
              <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed py-6 text-center">
                <p className="text-sm text-steel">No knowledge sources yet</p>
                {onCreateNew && (
                  <Button type="button" size="sm" onClick={onCreateNew}>
                    Create a new source
                  </Button>
                )}
              </div>
            ) : (
              <KnowledgeSourcePicker sources={sources} value={knowledgeSource} onChange={setKnowledgeSource} loading={loading} />
            )}
            {sources.length > 0 && onCreateNew && (
              <Button type="button" variant="link" className="h-auto p-0 text-xs" onClick={onCreateNew}>
                Don't see it? Create a new source
              </Button>
            )}
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
            <p className="text-xs text-steel-soft">
              Mandatory: context injected into every prompt. Optional: agent queries via search tool.
            </p>
          </div>

          <Accordion type="single" collapsible>
            <AccordionItem value="advanced" className="border-b-0">
              <AccordionTrigger className="text-sm">Advanced</AccordionTrigger>
              <AccordionContent>
                <KnowledgeAdvancedFields
                  priority={priority}
                  maxChunks={maxChunks}
                  tokenBudget={tokenBudget}
                  onPriority={setPriority}
                  onMaxChunks={setMaxChunks}
                  onTokenBudget={setTokenBudget}
                />
              </AccordionContent>
            </AccordionItem>
          </Accordion>

          <div className="space-y-2">
            <Label>Description</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description for this knowledge link"
              rows={2}
            />
          </div>
        </DialogScrollBody>

        <DialogScrollFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSave} disabled={!isValid}>
            {initialData ? 'Update' : 'Add'}
          </Button>
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
