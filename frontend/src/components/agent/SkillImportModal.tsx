import { useState, useEffect, useCallback } from 'react';
import { Search, Github, BookOpen, Download, CheckCircle2, AlertCircle, Loader2, ExternalLink } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { call } from '@/lib/frappe-sdk';
import { toast } from 'sonner';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { AgentSkillRef } from '@/types/agent.types';

// ─── Types ────────────────────────────────────────────────────────────────────

interface SkillPreview {
  skill_name: string;
  display_name: string;
  description: string;
  version?: string;
  author?: string;
  source_url?: string;
  content?: string;
  license?: string;
  compatibility?: string;
}

interface LibrarySkill {
  name: string;
  skill_name: string;
  display_name: string;
  description: string;
  version?: string;
  author?: string;
}

interface SkillImportModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedSkills: AgentSkillRef[];
  onAddSkills: (skills: AgentSkillRef[]) => void;
}

// ─── Known community repos (shown as quick-add suggestions) ───────────────────

const SUGGESTED_REPOS = [
  { repo: 'anthropics/skills', label: 'Anthropic Official Skills', description: 'Creative, development, enterprise & document skills curated by Anthropic' },
  { repo: 'vercel-labs/skills', label: 'Vercel Labs Skills', description: 'Frontend, deployment, and serverless workflow skills' },
  { repo: 'microsoft/azure-skills', label: 'Microsoft Azure Skills', description: 'Azure cloud operations and DevOps skills' },
];

// ─── Library tab ──────────────────────────────────────────────────────────────

function LibraryTab({
  refreshTrigger,
  selectedSkills,
  onSelect,
}: {
  refreshTrigger: number;
  selectedSkills: AgentSkillRef[];
  onSelect: (skill: LibrarySkill) => void;
}) {
  const [skills, setSkills] = useState<LibrarySkill[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);

  const selectedNames = new Set(selectedSkills.map((s) => s.skill));

  const load = useCallback(async (q: string) => {
    setLoading(true);
    try {
      const result = await call.get('huf.huf.doctype.skill.skill.get_skills', {
        search: q || undefined,
      });
      setSkills((result as { message: LibrarySkill[] }).message ?? []);
    } catch (e) {
      toast.error(getFrappeErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load('');
  }, [load, refreshTrigger]);

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value);
    load(e.target.value);
  };

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search skills…"
          className="pl-8"
          value={search}
          onChange={handleSearch}
        />
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin mr-2" />
          Loading…
        </div>
      ) : skills.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          <BookOpen className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No skills found. Import some from GitHub first.</p>
        </div>
      ) : (
        <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
          {skills.map((skill) => {
            const alreadyAdded = selectedNames.has(skill.skill_name);
            return (
              <div
                key={skill.skill_name}
                className="flex items-start gap-3 rounded-lg border p-3 hover:bg-accent/50 cursor-pointer transition-colors"
                onClick={() => !alreadyAdded && onSelect(skill)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">{skill.display_name}</span>
                    {skill.version && (
                      <Badge variant="outline" className="text-xs">{skill.version}</Badge>
                    )}
                    {skill.author && (
                      <span className="text-xs text-muted-foreground">by {skill.author}</span>
                    )}
                  </div>
                  {skill.description && (
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                      {skill.description}
                    </p>
                  )}
                </div>
                {alreadyAdded ? (
                  <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0 mt-0.5" />
                ) : (
                  <Button type="button" variant="outline" size="sm" className="shrink-0">
                    Add
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── GitHub importer tab ──────────────────────────────────────────────────────

function GitHubTab({ onImported }: { onImported: () => void }) {
  const [repo, setRepo] = useState('');
  const [token, setToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [previews, setPreviews] = useState<SkillPreview[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState('');

  const handlePreview = async () => {
    if (!repo.trim()) return;
    setPreviewing(true);
    setError('');
    setPreviews([]);
    setSelected(new Set());
    try {
      const result = await call.get('huf.huf.doctype.skill.skill.preview_github_skills', {
        repo: repo.trim(),
        github_token: token.trim() || undefined,
      });
      const list = (result as { message: SkillPreview[] }).message ?? [];
      setPreviews(list);
      setSelected(new Set(list.map((s) => s.skill_name)));
      if (list.length === 0) {
        setError('No SKILL.md files found in this repository. Check the repo slug and try again.');
      }
    } catch (e) {
      setError(getFrappeErrorMessage(e));
    } finally {
      setPreviewing(false);
    }
  };

  const handleImport = async () => {
    if (selected.size === 0) return;
    setImporting(true);
    try {
      const result = await call.get('huf.huf.doctype.skill.skill.import_github_skills', {
        repo: repo.trim(),
        skill_names: JSON.stringify([...selected]),
        github_token: token.trim() || undefined,
      });
      const res = (result as { message: { created: string[]; updated: string[]; skipped: string[] } }).message;
      const total = res.created.length + res.updated.length;
      toast.success(`Imported ${total} skill${total !== 1 ? 's' : ''} (${res.created.length} new, ${res.updated.length} updated)`);
      onImported();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e));
    } finally {
      setImporting(false);
    }
  };

  const toggleAll = () => {
    if (selected.size === previews.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(previews.map((s) => s.skill_name)));
    }
  };

  const toggleOne = (name: string) => {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setSelected(next);
  };

  return (
    <div className="space-y-4">
      {/* Suggested repos */}
      <div>
        <p className="text-xs text-muted-foreground mb-2">Popular community repos:</p>
        <div className="flex flex-wrap gap-2">
          {SUGGESTED_REPOS.map((s) => (
            <Button
              key={s.repo}
              type="button"
              variant="outline"
              size="sm"
              className="text-xs h-7"
              onClick={() => setRepo(s.repo)}
            >
              {s.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Repo input */}
      <div className="space-y-2">
        <Label className="text-xs">GitHub repo (owner/repo)</Label>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Github className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="e.g. anthropics/skills"
              className="pl-8"
              value={repo}
              onChange={(e) => { setRepo(e.target.value); setPreviews([]); setError(''); }}
              onKeyDown={(e) => e.key === 'Enter' && handlePreview()}
            />
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={handlePreview}
            disabled={!repo.trim() || previewing}
          >
            {previewing ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Fetch'}
          </Button>
        </div>
      </div>

      {/* Optional token */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <Label className="text-xs text-muted-foreground">GitHub token (optional — increases rate limit to 5 000 req/hr)</Label>
          <button
            type="button"
            className="text-xs text-muted-foreground underline"
            onClick={() => setShowToken(!showToken)}
          >
            {showToken ? 'hide' : 'show'}
          </button>
        </div>
        {showToken && (
          <Input
            type="password"
            placeholder="ghp_…"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="text-xs"
          />
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 rounded-md bg-destructive/10 text-destructive p-3 text-xs">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {/* Preview list */}
      {previews.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">{previews.length} skill{previews.length !== 1 ? 's' : ''} found</span>
            <button type="button" className="text-xs text-muted-foreground underline" onClick={toggleAll}>
              {selected.size === previews.length ? 'Deselect all' : 'Select all'}
            </button>
          </div>

          <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
            {previews.map((skill) => (
              <div
                key={skill.skill_name}
                className={`flex items-start gap-3 rounded-lg border p-2.5 cursor-pointer transition-colors ${selected.has(skill.skill_name) ? 'border-primary bg-primary/5' : 'hover:bg-accent/50'}`}
                onClick={() => toggleOne(skill.skill_name)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">{skill.display_name}</span>
                    {skill.version && <Badge variant="outline" className="text-xs">{skill.version}</Badge>}
                    {skill.author && <span className="text-xs text-muted-foreground">by {skill.author}</span>}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{skill.description}</p>
                  {skill.source_url && (
                    <a
                      href={skill.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground mt-0.5"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <ExternalLink className="h-3 w-3" />
                      View on GitHub
                    </a>
                  )}
                </div>
                <div className={`h-4 w-4 rounded-full border-2 shrink-0 mt-0.5 transition-colors ${selected.has(skill.skill_name) ? 'bg-primary border-primary' : 'border-muted-foreground'}`} />
              </div>
            ))}
          </div>

          <Button
            type="button"
            className="w-full"
            disabled={selected.size === 0 || importing}
            onClick={handleImport}
          >
            {importing ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <Download className="h-4 w-4 mr-2" />
            )}
            Import {selected.size} skill{selected.size !== 1 ? 's' : ''} to library
          </Button>
        </div>
      )}
    </div>
  );
}

// ─── Main modal ───────────────────────────────────────────────────────────────

export function SkillImportModal({
  open,
  onOpenChange,
  selectedSkills,
  onAddSkills,
}: SkillImportModalProps) {
  const [tab, setTab] = useState<'library' | 'github'>('library');
  const [refreshKey, setRefreshKey] = useState(0);

  const handleSelectFromLibrary = (skill: LibrarySkill) => {
    const alreadyAdded = selectedSkills.some((s) => s.skill === skill.skill_name);
    if (alreadyAdded) {
      toast.info(`${skill.display_name} is already attached.`);
      return;
    }
    const maxPriority = selectedSkills.reduce((m, s) => Math.max(m, s.priority ?? 0), 0);
    onAddSkills([
      {
        skill: skill.skill_name,
        mode: 'Optional',
        priority: maxPriority + 10,
        description: skill.description,
      },
    ]);
    toast.success(`Added "${skill.display_name}"`);
    onOpenChange(false);
  };

  const handleImported = () => {
    // Refresh library tab after import
    setRefreshKey((k) => k + 1);
    setTab('library');
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Add Skills</DialogTitle>
          <DialogDescription>
            Attach skills from your library or import new ones from any GitHub repository that
            follows the agentskills.io standard (Claude Code, OpenCode, Cursor, and 30+ others).
          </DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(v) => setTab(v as 'library' | 'github')}>
          <TabsList className="grid grid-cols-2">
            <TabsTrigger value="library">
              <BookOpen className="h-4 w-4 mr-1.5" />
              Skill Library
            </TabsTrigger>
            <TabsTrigger value="github">
              <Github className="h-4 w-4 mr-1.5" />
              Import from GitHub
            </TabsTrigger>
          </TabsList>

          <TabsContent value="library" className="mt-4">
            <LibraryTab
              refreshTrigger={refreshKey}
              selectedSkills={selectedSkills}
              onSelect={handleSelectFromLibrary}
            />
          </TabsContent>

          <TabsContent value="github" className="mt-4">
            <GitHubTab onImported={handleImported} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
