import { CircleHelp, ExternalLink } from 'lucide-react';
import { Button } from '../ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover';
import { Dialog, DialogContent, DialogTitle } from '../ui/dialog';
import { HIT_TARGET } from '@/lib/ui/responsive';
import { FIRST_RUN_STEPS, FLOW_GUIDE_URL, FLOW_SHORTCUTS } from '@/lib/flow/flowHelp';

/** What the help says: how a flow works, the keyboard shortcuts (not on a phone or tablet: no keyboard) and the full guide link. */
export function FlowHelpContent() {
  return (
    <div className="space-y-3 text-xs" data-testid="flow-help-popover">
      <div>
        <p className="text-sm font-semibold">How a flow works</p>
        <ol className="mt-1 list-decimal space-y-0.5 pl-4 text-muted-foreground">
          {FIRST_RUN_STEPS.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
        <p className="mt-1.5 text-muted-foreground">
          Run starts it once right now. Publish turns its trigger on, so it starts by itself. Unpublish turns it off.
        </p>
      </div>
      <div className="max-[1023px]:hidden">
        <p className="text-sm font-semibold">Keyboard shortcuts</p>
        <dl className="mt-1 space-y-1" data-testid="flow-help-shortcuts">
          {FLOW_SHORTCUTS.map((sc) => (
            <div key={sc.keys} className="flex items-start justify-between gap-3">
              <dt className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-eyebrow tracking-normal">{sc.keys}</dt>
              <dd className="text-right text-muted-foreground">{sc.does}</dd>
            </div>
          ))}
        </dl>
      </div>
      <a
        href={FLOW_GUIDE_URL}
        target="_blank"
        rel="noreferrer noopener"
        className="inline-flex items-center gap-1 font-medium text-primary underline underline-offset-2"
        data-testid="flow-help-guide-link"
      >
        Read the full guide to triggers and steps
        <ExternalLink className="w-3 h-3" aria-hidden />
      </a>
    </div>
  );
}

/** "?" button in the editor header: a popover with the help. */
export function FlowHelpPopover() {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className={`gap-2 ${HIT_TARGET}`} data-testid="flow-help" aria-label="Help" title="Help: how flows work and keyboard shortcuts">
          <CircleHelp className="w-4 h-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[340px] max-w-[calc(100vw-2rem)]">
        <FlowHelpContent />
      </PopoverContent>
    </Popover>
  );
}

/** The same help as a dialog, for the "..." menu (a menu item cannot open a popover of its own). */
export function FlowHelpDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]" data-testid="flow-help-dialog">
        <DialogTitle className="sr-only">Help</DialogTitle>
        <FlowHelpContent />
      </DialogContent>
    </Dialog>
  );
}
