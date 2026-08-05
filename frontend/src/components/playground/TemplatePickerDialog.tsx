import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2, Search } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { getAgentPrompts, type AgentPromptDoc } from '@/services/agentPromptApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface TemplatePickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onLoadTemplate: (prompt: AgentPromptDoc) => void;
}

export function TemplatePickerDialog({
  open,
  onOpenChange,
  onLoadTemplate,
}: TemplatePickerDialogProps) {
  const [prompts, setPrompts] = useState<AgentPromptDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setSearch('');
    let cancelled = false;
    getAgentPrompts({ status: 'active', limit: 100 })
      .then((response) => {
        if (!cancelled) {
          setPrompts(Array.isArray(response) ? response : response.items);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          toast.error(`Failed to load templates: ${getFrappeErrorMessage(error)}`);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const filtered = prompts.filter(
    (p) =>
      p.title.toLowerCase().includes(search.toLowerCase()) ||
      (p.description ?? '').toLowerCase().includes(search.toLowerCase()) ||
      (p.tags ?? '').toLowerCase().includes(search.toLowerCase()),
  );

  const handleSelect = (prompt: AgentPromptDoc) => {
    onLoadTemplate(prompt);
    onOpenChange(false);
    toast.success(`Loaded template: ${prompt.title}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Load template</DialogTitle>
          <DialogDescription>Load an active Agent Prompt template into the bench.</DialogDescription>
        </DialogHeader>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-steel" />
          <Input
            placeholder="Search templates..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <ScrollArea className="h-72 rounded border border-line">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-steel-soft" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="p-4 text-center text-sm text-steel">
              {search ? 'No templates match your search.' : 'No active templates found.'}
            </div>
          ) : (
            <div className="divide-y divide-line">
              {filtered.map((prompt) => (
                <Button
                  key={prompt.name}
                  type="button"
                  variant="ghost"
                  onClick={() => handleSelect(prompt)}
                  className="h-auto w-full items-start justify-start rounded-none px-3 py-2 text-left"
                >
                  <div className="w-full min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-medium">{prompt.title}</span>
                      <Badge variant="outline" size="sm" className="shrink-0">
                        {prompt.visibility || 'Private'}
                      </Badge>
                    </div>
                    {prompt.description ? (
                      <p className="mt-0.5 line-clamp-2 text-xs text-steel">{prompt.description}</p>
                    ) : null}
                    {prompt.tags ? (
                      <p className="mt-1 text-xs text-steel-soft">{prompt.tags}</p>
                    ) : null}
                  </div>
                </Button>
              ))}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
