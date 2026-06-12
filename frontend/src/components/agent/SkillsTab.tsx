import { useState } from 'react';
import { Plus, Sparkles, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Combobox } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { AgentSkillRow } from '@/types/skill.types';

interface SkillsTabProps {
  skills: AgentSkillRow[];
  skillOptions: { value: string; label: string; subtitle?: string }[];
  onChange: (skills: AgentSkillRow[]) => void;
}

export function SkillsTab({ skills, skillOptions, onChange }: SkillsTabProps) {
  const [selectedSkill, setSelectedSkill] = useState('');

  const handleAdd = () => {
    if (!selectedSkill || skills.some((s) => s.skill === selectedSkill)) return;
    const option = skillOptions.find((o) => o.value === selectedSkill);
    onChange([
      ...skills,
      {
        skill: selectedSkill,
        skill_name: option?.label,
        mode: 'Mandatory',
        auto_load: true,
        priority: 0,
        description: option?.subtitle || '',
      },
    ]);
    setSelectedSkill('');
  };

  const updateSkill = (index: number, patch: Partial<AgentSkillRow>) => {
    onChange(skills.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  };

  const removeSkill = (index: number) => {
    onChange(skills.filter((_, i) => i !== index));
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5" />
              Skills
            </CardTitle>
            <CardDescription>Reusable capability bundles attached to this agent</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Combobox
              options={skillOptions}
              value={selectedSkill}
              onValueChange={setSelectedSkill}
              placeholder="Select a skill..."
              searchPlaceholder="Search skills..."
              emptyText="No skills found"
            />
          </div>
          <Button type="button" size="sm" variant="outline" onClick={handleAdd} disabled={!selectedSkill}>
            <Plus className="w-4 h-4 mr-2" />
            Add Skill
          </Button>
        </div>

        {skills.length === 0 ? (
          <div className="text-center py-12 border border-dashed rounded-lg bg-muted/20">
            <p className="text-muted-foreground mb-2">No skills attached yet.</p>
            <p className="text-xs text-muted-foreground mb-4">
              Attach skills to give this agent access to bundled tools, knowledge, prompts, and MCP servers.
            </p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {skills.map((skill, index) => (
              <div
                key={skill.name || `skill-${index}`}
                className="flex flex-col gap-3 rounded-lg border p-4 hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="font-medium text-sm">{skill.skill_name || skill.skill}</h4>
                      <Badge
                        variant={skill.mode === 'Mandatory' ? 'default' : 'secondary'}
                        className="text-[10px] uppercase shrink-0"
                      >
                        {skill.mode}
                      </Badge>
                    </div>
                    {skill.description && (
                      <p className="text-xs text-muted-foreground line-clamp-2">{skill.description}</p>
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removeSkill(index)}
                    title="Remove skill"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <Select
                    value={skill.mode}
                    onValueChange={(value) => updateSkill(index, { mode: value as AgentSkillRow['mode'] })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Mode" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Mandatory">Mandatory</SelectItem>
                      <SelectItem value="Optional">Optional</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input
                    type="number"
                    placeholder="Priority"
                    value={skill.priority ?? 0}
                    onChange={(e) => updateSkill(index, { priority: Number(e.target.value) })}
                  />
                </div>
                <Input
                  placeholder="Description override (optional)"
                  value={skill.description || ''}
                  onChange={(e) => updateSkill(index, { description: e.target.value })}
                />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default SkillsTab;
