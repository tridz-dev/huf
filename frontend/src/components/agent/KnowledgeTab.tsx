import { Plus, BookOpen, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { AgentKnowledgeRow } from '@/types/agent.types';

interface KnowledgeTabProps {
  knowledgeSources: AgentKnowledgeRow[];
  onAdd: () => void;
  onEdit: (index: number) => void;
  onRemove: (index: number) => void;
}

export function KnowledgeTab({
  knowledgeSources,
  onAdd,
  onEdit,
  onRemove,
}: KnowledgeTabProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="w-5 h-5" />
              Knowledge Sources
            </CardTitle>
            <CardDescription>Knowledge sources available to this agent for RAG-based retrieval</CardDescription>
          </div>
          <Button size="sm" variant="outline" onClick={onAdd} type="button">
            <Plus className="w-4 h-4 mr-2" />
            Add Knowledge
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {knowledgeSources.length === 0 ? (
          <div className="text-center py-12 border border-dashed rounded-lg bg-muted/20">
            <p className="text-muted-foreground mb-2">No knowledge sources linked yet.</p>
            <p className="text-xs text-muted-foreground mb-4">
              Link knowledge sources so this agent can retrieve relevant context from indexed documents.
            </p>
            <Button onClick={onAdd} variant="outline" type="button">
              <Plus className="w-4 h-4 mr-2" />
              Add Knowledge
            </Button>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {knowledgeSources.map((ks, index) => (
              <div
                key={ks.name || `ks-${index}`}
                className="group flex flex-col lg:flex-row h-full lg:items-start lg:justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50 transition-colors"
              >
                <div className="flex-1 min-w-0 flex items-start gap-3">
                  <div className="mt-0.5 rounded-md border bg-muted/30 p-1.5 text-muted-foreground">
                    <BookOpen className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 space-y-1 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="font-medium text-sm">{ks.knowledge_source}</h4>
                      <Badge
                        variant={ks.mode === 'Mandatory' ? 'default' : 'secondary'}
                        className="text-[10px] uppercase shrink-0"
                      >
                        {ks.mode}
                      </Badge>
                      {ks.priority > 0 && (
                        <Badge variant="outline" className="text-xs shrink-0">
                          Priority {ks.priority}
                        </Badge>
                      )}
                    </div>
                    {ks.description && (
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {ks.description}
                      </p>
                    )}
                    <div className="flex items-center gap-3 text-xs text-muted-foreground pt-1">
                      <span>Max chunks: {ks.max_chunks}</span>
                      <span>Token budget: {ks.token_budget}</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1 mt-2 lg:mt-0 opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => onEdit(index)}
                    title="Edit"
                  >
                    <Edit className="w-4 h-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => onRemove(index)}
                    title="Remove"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
