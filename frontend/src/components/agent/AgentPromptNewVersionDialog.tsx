import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';

interface AgentPromptNewVersionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dialogTitle?: string;
  title: string;
  description: string;
  showDescription?: boolean;
  titleLabel?: string;
  titlePlaceholder?: string;
  descriptionLabel?: string;
  descriptionPlaceholder?: string;
  confirmLabel?: string;
  onTitleChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onConfirm: () => void;
  saving: boolean;
}

export function AgentPromptNewVersionDialog({
  open,
  onOpenChange,
  dialogTitle = 'Create New Version',
  title,
  description,
  showDescription = true,
  titleLabel = 'Title (Optional)',
  titlePlaceholder = 'Leave as is to keep the same title',
  descriptionLabel = 'Description (Optional)',
  descriptionPlaceholder = 'Optional description for this version',
  confirmLabel = 'Create',
  onTitleChange,
  onDescriptionChange,
  onConfirm,
  saving,
}: AgentPromptNewVersionDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{dialogTitle}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="new-version-title">{titleLabel}</Label>
            <Input
              id="new-version-title"
              value={title}
              onChange={(event) => onTitleChange(event.target.value)}
              placeholder={titlePlaceholder}
            />
          </div>
          {showDescription ? (
            <div className="space-y-2">
              <Label htmlFor="new-version-description">{descriptionLabel}</Label>
              <Textarea
                id="new-version-description"
                value={description}
                onChange={(event) => onDescriptionChange(event.target.value)}
                placeholder={descriptionPlaceholder}
                rows={3}
              />
            </div>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="button" onClick={onConfirm} disabled={saving}>
              {saving ? 'Saving...' : confirmLabel}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
