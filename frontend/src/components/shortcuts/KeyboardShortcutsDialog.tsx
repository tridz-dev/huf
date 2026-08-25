import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { ShortcutKey } from '@/components/ui/shortcut-key';
import { SHORTCUTS, formatBinding, type ShortcutScope } from '@/lib/shortcuts/registry';
import { usePlatform } from '@/lib/shortcuts/platform';

const SCOPE_ORDER: ShortcutScope[] = ['Global', 'Chat', 'Playground', 'Sidebar'];

interface KeyboardShortcutsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KeyboardShortcutsDialog({ open, onOpenChange }: KeyboardShortcutsDialogProps) {
  const platform = usePlatform();

  const groups = SCOPE_ORDER.map((scope) => ({
    scope,
    shortcuts: SHORTCUTS.filter((s) => s.scope === scope),
  })).filter((group) => group.shortcuts.length > 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>Speed up common actions across the app.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-5">
          {groups.map((group) => (
            <div key={group.scope} className="flex flex-col gap-2">
              <h3 className="text-xs font-medium uppercase tracking-wide text-steel-soft">
                {group.scope}
              </h3>
              <div className="flex flex-col gap-2">
                {group.shortcuts.map((shortcut) => (
                  <div key={shortcut.id} className="flex items-center justify-between gap-4">
                    <span className="text-sm text-ink">{shortcut.description}</span>
                    <ShortcutKey keys={formatBinding(shortcut.binding, platform)} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
