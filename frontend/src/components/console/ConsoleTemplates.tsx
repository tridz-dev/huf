import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Search, Loader2, Plus, ArrowRight } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { getAgentPrompts, type AgentPromptDoc } from '@/services/agentPromptApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface ConsoleTemplatesProps {
  onLoadTemplate: (prompt: AgentPromptDoc) => void;
}

export function ConsoleTemplates({ onLoadTemplate }: ConsoleTemplatesProps) {
  const navigate = useNavigate();
  const [prompts, setPrompts] = useState<AgentPromptDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    setLoading(true);
    let cancelled = false;
    getAgentPrompts({ status: 'all', limit: 200 })
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
  }, []);

  const filtered = prompts.filter(
    (p) =>
      p.title.toLowerCase().includes(search.toLowerCase()) ||
      (p.description ?? '').toLowerCase().includes(search.toLowerCase()) ||
      (p.tags ?? '').toLowerCase().includes(search.toLowerCase()),
  );

  const handleLoad = (prompt: AgentPromptDoc) => {
    onLoadTemplate(prompt);
    toast.success(`Loaded template: ${prompt.title}`);
  };

  return (
    <div className="flex h-full flex-col p-4">
      <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Prompt templates</h2>
          <p className="text-sm text-steel">Browse and load reusable Agent Prompt templates.</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-steel" />
            <Input
              placeholder="Search templates..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <Button size="sm" onClick={() => navigate('/prompts/new')}>
            <Plus className="mr-1.5 h-4 w-4" />
            New
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        {loading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-steel-soft" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-2 text-sm text-steel">
            <p>{search ? 'No templates match your search.' : 'No templates found.'}</p>
            <Button variant="outline" size="sm" onClick={() => navigate('/prompts/new')}>
              Create your first template
            </Button>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((prompt) => (
              <Card key={prompt.name} className="flex flex-col">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base">{prompt.title}</CardTitle>
                    <Badge variant={prompt.is_active ? 'success' : 'secondary'} className="shrink-0">
                      {prompt.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </div>
                  <CardDescription className="line-clamp-2">
                    {prompt.description || 'No description'}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col justify-end gap-3">
                  <div className="flex flex-wrap gap-1">
                    <Badge variant="outline">{prompt.visibility || 'Private'}</Badge>
                    {prompt.tags
                      ? prompt.tags.split(',').map((tag) => (
                          <Badge key={tag} variant="outline" className="text-xs">
                            {tag.trim()}
                          </Badge>
                        ))
                      : null}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button size="sm" className="flex-1 gap-1.5" onClick={() => handleLoad(prompt)}>
                      <ArrowRight className="h-4 w-4" />
                      Load into Playground
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
