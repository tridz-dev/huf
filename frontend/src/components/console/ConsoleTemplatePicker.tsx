import { useState, useEffect } from 'react';
import { Search, BookOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Loader2 } from 'lucide-react';
import { getAgentPrompts, type AgentPromptDoc } from '@/services/agentPromptApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { toast } from 'sonner';

interface ConsoleTemplatePickerProps {
  onLoadTemplate: (prompt: AgentPromptDoc) => void;
}

export function ConsoleTemplatePicker({ onLoadTemplate }: ConsoleTemplatePickerProps) {
  const [open, setOpen] = useState(false);
  const [prompts, setPrompts] = useState<AgentPromptDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (!open) return;
    setLoading(true);
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
    setOpen(false);
    toast.success(`Loaded template: ${prompt.title}`);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size="sm" variant="outline" className="gap-1.5">
          <BookOpen className="h-4 w-4" />
          Templates
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end">
        <div className="border-b border-line p-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-steel" />
            <Input
              placeholder="Search templates..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>
        <ScrollArea className="h-72">
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
                <button
                  key={prompt.name}
                  type="button"
                  onClick={() => handleSelect(prompt)}
                  className="w-full px-3 py-2 text-left transition-colors hover:bg-paper-deep"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-medium">{prompt.title}</span>
                    <Badge variant="outline" className="shrink-0 text-xs">
                      {prompt.visibility || 'Private'}
                    </Badge>
                  </div>
                  {prompt.description ? (
                    <p className="mt-0.5 line-clamp-2 text-xs text-steel">{prompt.description}</p>
                  ) : null}
                  {prompt.tags ? (
                    <p className="mt-1 text-xs text-steel-soft">{prompt.tags}</p>
                  ) : null}
                </button>
              ))}
            </div>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}
