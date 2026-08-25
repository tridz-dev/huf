import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { savePromptTemplate, type SavePromptTemplateResult } from '@/services/consoleApi';
import {
  updateAgentPrompt,
  createAgentPromptNewVersion,
  forkAgentPrompt,
  type AgentPromptDoc,
} from '@/services/agentPromptApi';
import { getCategories, type CategoryDoc } from '@/services/categoryApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

type SaveMode = 'new' | 'update' | 'version' | 'fork';

export interface SaveTemplateResult {
  mode: SaveMode;
  name: string;
  title?: string;
  version?: number;
}

interface SaveTemplateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  promptBody: string;
  /** The Agent Prompt currently loaded into the bench, if any — enables update/version/fork. */
  loadedTemplate?: Pick<AgentPromptDoc, 'name' | 'title' | 'version'> | null;
  onSaved?: (result: SaveTemplateResult) => void;
}

export function SaveTemplateDialog({
  open,
  onOpenChange,
  promptBody,
  loadedTemplate,
  onSaved,
}: SaveTemplateDialogProps) {
  const [mode, setMode] = useState<SaveMode>('new');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<'Public' | 'App' | 'Private'>('Private');
  const [category, setCategory] = useState('');
  const [tags, setTags] = useState('');
  const [categories, setCategories] = useState<CategoryDoc[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    getCategories()
      .then((data) => {
        if (!cancelled) setCategories(data);
      })
      .catch(() => {
        // Categories are optional; failure is non-blocking.
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (open) {
      setMode(loadedTemplate ? 'version' : 'new');
      setTitle('');
      setDescription('');
      setVisibility('Private');
      setCategory('');
      setTags('');
    }
  }, [open, loadedTemplate]);

  const handleSave = async () => {
    if (mode === 'new' && !title.trim()) {
      toast.error('Title is required');
      return;
    }
    setSaving(true);
    try {
      if (mode === 'new') {
        const result: SavePromptTemplateResult = await savePromptTemplate({
          prompt_body: promptBody,
          title: title.trim(),
          description: description.trim() || undefined,
          visibility,
          category: category || undefined,
          tags: tags.trim() || undefined,
        });
        toast.success('Prompt saved as template');
        onSaved?.({ mode, name: result.name, title: title.trim(), version: result.version });
      } else if (mode === 'update' && loadedTemplate) {
        const result = await updateAgentPrompt(loadedTemplate.name, {
          prompt_body: promptBody,
          ...(title.trim() && { title: title.trim() }),
          ...(description.trim() && { description: description.trim() }),
        });
        toast.success('Template updated');
        onSaved?.({ mode, name: result.name, title: result.title, version: result.version });
      } else if (mode === 'version' && loadedTemplate) {
        const result = await createAgentPromptNewVersion(
          loadedTemplate.name,
          promptBody,
          title.trim() || undefined,
          description.trim() || undefined,
        );
        toast.success(`Saved as version ${result.version}`);
        onSaved?.({ mode, name: result.name, title: title.trim() || loadedTemplate.title, version: result.version });
      } else if (mode === 'fork' && loadedTemplate) {
        const result = await forkAgentPrompt(loadedTemplate.name, title.trim() || undefined);
        toast.success('Forked as a new template');
        onSaved?.({ mode, name: result.name, title: title.trim() || undefined, version: result.version });
      }
      onOpenChange(false);
    } catch (error) {
      toast.error(`Failed to save template: ${getFrappeErrorMessage(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const saveLabel =
    mode === 'update'
      ? 'Update template'
      : mode === 'version'
        ? 'Save as new version'
        : mode === 'fork'
          ? 'Fork template'
          : 'Save template';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Save as template</DialogTitle>
          <DialogDescription>
            {loadedTemplate
              ? `"${loadedTemplate.title}" is currently loaded. Choose how to save your changes.`
              : 'Save the current prompt as a reusable Agent Prompt template.'}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          {loadedTemplate && (
            <RadioGroup
              value={mode}
              onValueChange={(v) => setMode(v as SaveMode)}
              className="gap-2.5"
            >
              <label className="flex items-start gap-2.5 text-sm">
                <RadioGroupItem value="update" className="mt-0.5" />
                <span>
                  <span className="font-medium">Update this template</span>
                  <span className="block text-xs text-steel">
                    Overwrite “{loadedTemplate.title}” in place.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2.5 text-sm">
                <RadioGroupItem value="version" className="mt-0.5" />
                <span>
                  <span className="font-medium">Save as new version</span>
                  <span className="block text-xs text-steel">
                    Keep the current version and publish a new one in its place.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2.5 text-sm">
                <RadioGroupItem value="fork" className="mt-0.5" />
                <span>
                  <span className="font-medium">Fork as new template</span>
                  <span className="block text-xs text-steel">
                    Create an independent copy, unlinked from “{loadedTemplate.title}”.
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2.5 text-sm">
                <RadioGroupItem value="new" className="mt-0.5" />
                <span>
                  <span className="font-medium">Save as new template</span>
                  <span className="block text-xs text-steel">Start an unrelated template.</span>
                </span>
              </label>
            </RadioGroup>
          )}

          <div className="space-y-2">
            <Label htmlFor="template-title">Title</Label>
            <Input
              id="template-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={
                mode === 'new' || !loadedTemplate
                  ? 'e.g. Customer support greeting'
                  : `Defaults to "${loadedTemplate.title}"`
              }
            />
          </div>
          {mode !== 'fork' && (
            <div className="space-y-2">
              <Label htmlFor="template-description">Description</Label>
              <Textarea
                id="template-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What is this prompt for?"
                rows={2}
              />
            </div>
          )}
          {mode === 'new' && (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Visibility</Label>
                  <Select value={visibility} onValueChange={(v) => setVisibility(v as typeof visibility)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Private">Private</SelectItem>
                      <SelectItem value="App">App</SelectItem>
                      <SelectItem value="Public">Public</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Category</Label>
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger>
                      <SelectValue placeholder="None" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">None</SelectItem>
                      {categories.map((c) => (
                        <SelectItem key={c.name} value={c.name}>
                          {c.category_name || c.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="template-tags">Tags</Label>
                <Input
                  id="template-tags"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="Comma-separated tags"
                />
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving || (mode === 'new' && !title.trim())}>
            {saving ? 'Saving...' : saveLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
