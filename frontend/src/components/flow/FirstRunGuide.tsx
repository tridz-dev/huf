import { useState, type CSSProperties } from 'react';
import { useStore } from 'reactflow';
import { X } from 'lucide-react';
import { Button } from '../ui/button';
import { cn } from '@/lib/utils';
import { FIRST_RUN_STEPS } from '@/lib/flow/flowHelp';

const KEY = 'huf.flow.firstRunGuide.dismissed';
const CARD_WIDTH = 288;
const GAP = 16;

function dismissedBefore(): boolean {
  try {
    return window.localStorage.getItem(KEY) === '1';
  } catch {
    return false;
  }
}

const place = (left: number, top: number): CSSProperties => ({ left, top, width: CARD_WIDTH });

/**
 * Coach mark for an empty canvas: points at the trigger step and says what to do first. It sits beside the trigger
 * (below the first "Add step" card when the canvas is too narrow), moves with the canvas, and can be closed for
 * good; the header Help button repeats it.
 */
export function FirstRunGuide() {
  const [hidden, setHidden] = useState(dismissedBefore);
  const anchor = useStore((s) => {
    const nodes = [...s.nodeInternals.values()];
    if (nodes.length === 0) return null;
    const [tx, ty, zoom] = s.transform;
    const box = (n: (typeof nodes)[number]) => {
      const p = n.positionAbsolute ?? n.position;
      return { left: p.x * zoom + tx, top: p.y * zoom + ty, right: (p.x + (n.width ?? 236)) * zoom + tx, bottom: (p.y + (n.height ?? 70)) * zoom + ty };
    };
    const trigger = nodes.find((n) => (n.data as { nodeType?: string })?.nodeType === 'trigger') ?? nodes[0];
    const t = box(trigger);
    const lowest = Math.max(...nodes.map((n) => box(n).bottom));
    return `${Math.round(t.right)}|${Math.round(t.top)}|${Math.round(t.left)}|${Math.round(lowest)}|${s.width}`;
  });
  if (hidden || !anchor) return null;
  const [right, top, left, lowest, canvasWidth] = anchor.split('|').map(Number);
  const beside = canvasWidth - right >= CARD_WIDTH + GAP + 8;
  const style = beside
    ? place(right + GAP, Math.max(top, 8))
    : place(Math.min(Math.max(left + (right - left) / 2 - CARD_WIDTH / 2, 8), Math.max(canvasWidth - CARD_WIDTH - 8, 8)), lowest + GAP);
  return (
    <div
      className="pointer-events-auto absolute z-10 rounded-lg border border-signal/50 bg-card p-3 text-xs shadow-md"
      style={style}
      role="note"
      data-testid="flow-first-run-guide"
      data-placement={beside ? 'beside-trigger' : 'below'}
    >
      <span
        aria-hidden
        className={cn('absolute h-3 w-3 rotate-45 border-signal/50 bg-card', beside ? '-left-1.5 top-5 border-b border-l' : '-top-1.5 left-1/2 -ml-1.5 border-l border-t')}
      />
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold">Start here: build your first flow</p>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Hide this guide"
          title="Hide this guide"
          data-testid="flow-first-run-guide-close"
          onClick={() => {
            try {
              window.localStorage.setItem(KEY, '1');
            } catch {
              /* ignore: the guide just comes back next time */
            }
            setHidden(true);
          }}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
      <ol className="mt-1 list-decimal space-y-0.5 pl-4 text-muted-foreground">
        {FIRST_RUN_STEPS.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      <p className="mt-1.5 text-muted-foreground">Need more? Use the ? button at the top for tips and shortcuts.</p>
    </div>
  );
}
