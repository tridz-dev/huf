import { useState } from 'react';
import { Copy, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { copyText } from '@/lib/clipboard';
import {
  SKILL_SOURCES_EXAMPLE,
  jsonFromRows,
  rowsFromJsonText,
  type SkillSourceRow,
} from '@/lib/skills/skillSources';

const JSON_CHOICE_KEY = 'huf.skillSources.asJson';

function readChoice(): boolean {
  try {
    return window.localStorage.getItem(JSON_CHOICE_KEY) === '1';
  } catch {
    return false;
  }
}

interface SkillSourcesEditorProps {
  rows: SkillSourceRow[];
  onChange: (rows: SkillSourceRow[]) => void;
}

/** Friendly list of skill sources, with "Edit as JSON" for people who prefer to paste one. */
export function SkillSourcesEditor({ rows, onChange }: SkillSourcesEditorProps) {
  const [asJson, setAsJson] = useState(readChoice);
  const [text, setText] = useState(() => jsonFromRows(rows));
  const [jsonError, setJsonError] = useState<string | null>(null);

  const choose = (next: boolean) => {
    if (next) {
      setText(jsonFromRows(rows));
      setJsonError(null);
    }
    setAsJson(next);
    try {
      window.localStorage.setItem(JSON_CHOICE_KEY, next ? '1' : '0');
    } catch {
      /* the choice is only a convenience */
    }
  };

  const update = (index: number, patch: Partial<SkillSourceRow>) =>
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const onText = (value: string) => {
    setText(value);
    const parsed = rowsFromJsonText(value);
    if ('error' in parsed) setJsonError(parsed.error);
    else {
      setJsonError(null);
      onChange(parsed.rows);
    }
  };

  return (
    <div className="space-y-4" data-testid="skill-sources-editor">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          Each source is a repository folder that holds skills. They appear in the skill import window.
        </p>
        <div className="flex shrink-0 items-center gap-2 text-sm">
          <Switch id="skill-sources-as-json" checked={asJson} onCheckedChange={choose} data-testid="skill-sources-json-toggle" />
          <Label htmlFor="skill-sources-as-json" className="font-normal">Edit as JSON</Label>
        </div>
      </div>

      {asJson ? (
        <div className="space-y-2" data-testid="skill-sources-json">
          <Label htmlFor="skill_sources_json">Sources (JSON)</Label>
          <p className="text-xs text-muted-foreground">
            One entry per source, named by its key. Each needs a <code>repo_url</code>; <code>path</code> (folder) and{' '}
            <code>ref</code> (branch) are optional. If the text is not valid, the list is not changed and you can keep typing.
          </p>
          <Textarea
            id="skill_sources_json"
            data-testid="skill-sources-json-input"
            value={text}
            onChange={(e) => onText(e.target.value)}
            spellCheck={false}
            className="min-h-[220px] font-mono text-sm"
            aria-invalid={jsonError ? true : undefined}
          />
          {jsonError && (
            <p className="text-sm text-destructive" role="alert" data-testid="skill-sources-json-error">
              {jsonError}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" disabled={Boolean(jsonError)} onClick={() => setText(jsonFromRows(rows))}>
              Format
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => void copyText(SKILL_SOURCES_EXAMPLE)}>
              <Copy className="mr-1.5 h-3.5 w-3.5" /> Copy example
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {rows.map((row, index) => (
            <div key={index} className="grid gap-3 rounded-md border p-3 sm:grid-cols-2" data-testid={`skill-source-row-${index}`}>
              <div className="space-y-1.5">
                <Label htmlFor={`skill-name-${index}`}>Name</Label>
                <Input id={`skill-name-${index}`} value={row.name} onChange={(e) => update(index, { name: e.target.value })} placeholder="my-skills" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`skill-url-${index}`}>Repository link</Label>
                <Input id={`skill-url-${index}`} value={row.repo_url} onChange={(e) => update(index, { repo_url: e.target.value })} placeholder="https://github.com/your-team/your-skills" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor={`skill-path-${index}`}>Folder</Label>
                <Input id={`skill-path-${index}`} value={row.path} onChange={(e) => update(index, { path: e.target.value })} placeholder="skills" />
              </div>
              <div className="flex items-end gap-2">
                <div className="min-w-0 flex-1 space-y-1.5">
                  <Label htmlFor={`skill-ref-${index}`}>Branch</Label>
                  <Input id={`skill-ref-${index}`} value={row.ref} onChange={(e) => update(index, { ref: e.target.value })} placeholder="main" />
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove ${row.name || 'this source'}`}
                  className="text-destructive hover:text-destructive"
                  onClick={() => onChange(rows.filter((_, i) => i !== index))}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={() => onChange([...rows, { name: '', repo_url: '', path: 'skills', ref: 'main' }])} data-testid="skill-source-add">
            <Plus className="mr-1.5 h-4 w-4" /> Add a source
          </Button>
        </div>
      )}
    </div>
  );
}
