import { Plus, Trash2, ArrowUp, ArrowDown, BookOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { AgentSkillRef } from '@/types/agent.types';

interface SkillsTabProps {
  selectedSkills: AgentSkillRef[];
  onAddSkills: () => void;
  onRemoveSkill: (skillName: string) => void;
  onChangeMode: (skillName: string, mode: 'Mandatory' | 'Optional') => void;
  onChangePriority: (skillName: string, direction: 'up' | 'down') => void;
}

export function SkillsTab({
  selectedSkills,
  onAddSkills,
  onRemoveSkill,
  onChangeMode,
  onChangePriority,
}: SkillsTabProps) {
  const sorted = [...selectedSkills].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">Agent Skills</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Skills are reusable instruction packages. <strong>Mandatory</strong> skills are always
            injected into the system prompt; <strong>Optional</strong> skills are listed for the
            agent to load on demand via the <code className="text-xs">load_skill</code> tool.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onAddSkills}>
          <Plus className="h-4 w-4 mr-1" />
          Add Skill
        </Button>
      </div>

      {sorted.length === 0 ? (
        <div className="border border-dashed rounded-lg p-8 text-center text-muted-foreground">
          <BookOpen className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm font-medium">No skills attached</p>
          <p className="text-xs mt-1">
            Add skills to give this agent reusable workflow knowledge, or import community skills
            from GitHub.
          </p>
          <Button type="button" variant="outline" size="sm" className="mt-3" onClick={onAddSkills}>
            <Plus className="h-4 w-4 mr-1" />
            Add Skill
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map((row, idx) => (
            <div
              key={row.skill}
              className="flex items-start gap-3 rounded-lg border bg-card p-3"
            >
              {/* Priority controls */}
              <div className="flex flex-col gap-0.5 pt-0.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5"
                  disabled={idx === 0}
                  onClick={() => onChangePriority(row.skill, 'up')}
                >
                  <ArrowUp className="h-3 w-3" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5"
                  disabled={idx === sorted.length - 1}
                  onClick={() => onChangePriority(row.skill, 'down')}
                >
                  <ArrowDown className="h-3 w-3" />
                </Button>
              </div>

              {/* Skill info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium truncate">{row.skill}</span>
                  <Badge
                    variant={row.mode === 'Mandatory' ? 'default' : 'secondary'}
                    className="text-xs shrink-0"
                  >
                    {row.mode}
                  </Badge>
                </div>
                {row.description && (
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {row.description}
                  </p>
                )}
              </div>

              {/* Mode selector */}
              <Select
                value={row.mode}
                onValueChange={(v) => onChangeMode(row.skill, v as 'Mandatory' | 'Optional')}
              >
                <SelectTrigger className="h-7 w-28 text-xs shrink-0">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Optional">Optional</SelectItem>
                  <SelectItem value="Mandatory">Mandatory</SelectItem>
                </SelectContent>
              </Select>

              {/* Remove */}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0 text-muted-foreground hover:text-destructive"
                onClick={() => onRemoveSkill(row.skill)}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Skills are loaded in priority order (highest first). Drag or use arrows to reorder.
      </p>
    </div>
  );
}
