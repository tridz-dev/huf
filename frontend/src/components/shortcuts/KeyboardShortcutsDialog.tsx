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
import { useLocation } from 'react-router-dom';
import { useViewport } from '@/lib/ui/responsive';

const SCOPE_ORDER: ShortcutScope[] = ['Global', 'Flow editor', 'Chat', 'Playground', 'Sidebar'];
/** Inside a flow the editor's own shortcuts come first. */
const FLOW_SCOPE_ORDER: ShortcutScope[] = ['Flow editor', 'Global', 'Chat', 'Playground', 'Sidebar'];

interface KeyboardShortcutsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KeyboardShortcutsDialog({ open, onOpenChange }: KeyboardShortcutsDialogProps) {
  const platform = usePlatform();

  const { pathname } = useLocation();
  const { isPhone } = useViewport();
  const inFlow = /^\/flows\/[^/]+/.test(pathname);
  // A phone only reads flows: the editor's keys do not apply there, so they are not listed.
  const scopes = (inFlow ? FLOW_SCOPE_ORDER : SCOPE_ORDER).filter((scope) => scope !== 'Flow editor' || (inFlow && !isPhone));
  const groups = scopes.map((scope) => ({
    scope,
    // The editor has its own Save line; the general one would list it twice.
    shortcuts: SHORTCUTS.filter((s) => s.scope === scope && !(inFlow && s.id === 'save')),
  })).filter((group) => group.shortcuts.length > 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-testid="shortcuts-dialog">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>Speed up common actions across the app.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-5">
          {groups.map((group) => (
            <div key={group.scope} className="flex flex-col gap-2">
              <h3 className="text-xs font-medium uppercase tracking-wide text-steel" data-testid={`shortcuts-group-${group.scope.toLowerCase().replace(/ /g, '-')}`}>
                {group.scope}
              </h3>
              <div className="flex flex-col gap-2">
                {group.shortcuts.map((shortcut) => (
                  <div key={shortcut.id} className="flex items-center justify-between gap-4">
                    <span className="text-sm text-ink">{shortcut.description}</span>
                    <ShortcutKey keys={shortcut.keys ?? formatBinding(shortcut.binding, platform)} />
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
