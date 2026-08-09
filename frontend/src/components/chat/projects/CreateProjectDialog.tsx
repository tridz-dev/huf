// A7: Create-project dialog opened from the Projects landing page's
// "+ Project" button. Collects project_name (required) plus optional
// description/instructions, then delegates to projectApi.createProject.
// The caller (ChatProjectsPage) owns list refresh + navigate-to-detail
// after a successful create - this component only knows how to submit.

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { createProject, type HufProject } from '@/services/projectApi';

export interface CreateProjectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fired after the project is created successfully. */
  onCreated: (project: HufProject) => void;
}

export function CreateProjectDialog({ open, onOpenChange, onCreated }: CreateProjectDialogProps) {
  const [projectName, setProjectName] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const resetForm = () => {
    setProjectName('');
    setDescription('');
    setInstructions('');
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && !submitting) {
      resetForm();
    }
    onOpenChange(nextOpen);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = projectName.trim();
    if (!trimmedName || submitting) return;

    setSubmitting(true);
    try {
      const project = await createProject({
        project_name: trimmedName,
        description: description.trim() || undefined,
        instructions: instructions.trim() || undefined,
      });
      resetForm();
      onOpenChange(false);
      onCreated(project);
    } catch {
      // createProject already surfaces the error via handleFrappeError.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>New project</DialogTitle>
            <DialogDescription>
              Projects group related conversations so they share context, files, and instructions.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-4 py-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="project-name">Name</Label>
              <Input
                id="project-name"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder="e.g. Q3 launch plan"
                autoFocus
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="project-description">
                Description <span className="text-steel-soft font-normal">(optional)</span>
              </Label>
              <Textarea
                id="project-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What is this project for?"
                rows={2}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="project-instructions">
                Instructions <span className="text-steel-soft font-normal">(optional)</span>
              </Label>
              <Textarea
                id="project-instructions"
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                placeholder="Context or guidance every chat in this project should have."
                rows={3}
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" disabled={!projectName.trim() || submitting}>
              {submitting ? 'Creating...' : 'Create project'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
