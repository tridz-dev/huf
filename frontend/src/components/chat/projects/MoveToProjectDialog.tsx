// A12: small picker used by ConversationMenu's "Move to Project…" /
// "Move to another Project…" actions. Unlike CreateProjectDialog this never
// creates a project - it only lists existing ones (reusing projectApi's
// listProjects, same source ChatProjectsPage uses) and lets the user pick
// one to move the conversation into.

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { listProjects, type HufProject } from '@/services/projectApi';
import { cn } from '@/lib/utils';

export interface MoveToProjectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Project the conversation currently belongs to, if any - excluded from
   * the picker since moving "into" the same project is a no-op. */
  currentProject?: string | null;
  /** Called with the chosen HUF Project name once the user confirms. */
  onMove: (project: string) => void;
}

export function MoveToProjectDialog({ open, onOpenChange, currentProject, onMove }: MoveToProjectDialogProps) {
  const [projects, setProjects] = useState<HufProject[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSelected(null);
    setLoading(true);
    listProjects({ status: 'Open' })
      .then((result) => setProjects(result))
      .finally(() => setLoading(false));
  }, [open]);

  const selectableProjects = projects.filter((p) => p.name !== currentProject);

  const handleConfirm = async () => {
    if (!selected || submitting) return;
    setSubmitting(true);
    try {
      onMove(selected);
      onOpenChange(false);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>Move to Project</DialogTitle>
          <DialogDescription>Choose a project to move this conversation into.</DialogDescription>
        </DialogHeader>

        <div className="flex max-h-72 flex-col gap-1 overflow-y-auto py-2">
          {loading ? (
            <div className="px-2 py-3 text-center text-[13px] text-steel">Loading projects...</div>
          ) : selectableProjects.length === 0 ? (
            <div className="px-2 py-3 text-center text-[13px] text-steel">No other projects available.</div>
          ) : (
            selectableProjects.map((project) => (
              <button
                key={project.name}
                type="button"
                onClick={() => setSelected(project.name)}
                className={cn(
                  'flex items-center rounded-md px-3 py-2 text-left text-[13px] transition-colors',
                  selected === project.name ? 'bg-paper-deep text-ink' : 'hover:bg-paper-deep/60'
                )}
              >
                {project.project_name}
              </button>
            ))
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button type="button" onClick={handleConfirm} disabled={!selected || submitting}>
            {submitting ? 'Moving...' : 'Move'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
