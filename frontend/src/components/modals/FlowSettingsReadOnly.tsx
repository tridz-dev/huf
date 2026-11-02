import { Dialog, DialogDescription, DialogTitle } from '../ui/dialog';
import { DialogScrollBody, DialogScrollContent, DialogScrollFooter, DialogScrollHeader } from '../ui/dialog-scroll';
import { Button } from '../ui/button';

interface FlowSettingsReadOnlyProps {
  open: boolean;
  onClose: () => void;
  name: string;
  description: string;
  category: string;
}

function Row({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <div className="grid gap-1">
      <dt className="text-meta font-medium text-muted-foreground">{label}</dt>
      <dd className="whitespace-pre-wrap break-words text-sm" data-testid={testId}>
        {value || <span className="italic text-muted-foreground">Not set</span>}
      </dd>
    </div>
  );
}

/** What the flow settings dialog shows people who cannot edit the flow: the details as plain text and a Close button. */
export function FlowSettingsReadOnly({ open, onClose, name, description, category }: FlowSettingsReadOnlyProps) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogScrollContent className="sm:max-w-[425px]" data-testid="flow-settings-modal">
        <DialogScrollHeader>
          <DialogTitle>Flow settings</DialogTitle>
          <DialogDescription>The name, description and category show up in the flows list.</DialogDescription>
        </DialogScrollHeader>
        <DialogScrollBody className="grid gap-4 py-4">
          <p role="status" className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground" data-testid="flow-settings-view-only">
            View only: you can read these details, not change them. A flow editor can change them.
          </p>
          <dl className="grid gap-4">
            <Row label="Flow name" value={name} testId="flow-settings-name-value" />
            <Row label="Description" value={description} testId="flow-settings-description-value" />
            <Row label="Category" value={category || 'Uncategorized'} testId="flow-settings-category-value" />
          </dl>
        </DialogScrollBody>
        <DialogScrollFooter className="justify-end">
          <Button variant="outline" size="sm" data-testid="flow-settings-close" onClick={onClose}>
            Close
          </Button>
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
