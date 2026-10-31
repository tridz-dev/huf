import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { HumanItem, HumanNode } from '@/lib/flow-run/humanize';

export const LIST_PAGE = 10;

/** Text that may be long: the first lines with "Show more", the whole text one click away. */
export function LongText({ node, testId }: { node: Extract<HumanNode, { kind: 'text' }>; testId: string }) {
  const [open, setOpen] = useState(false);
  if (!node.long) return <span className="break-words whitespace-pre-wrap" data-testid={testId}>{node.text}</span>;
  return (
    <span className="break-words whitespace-pre-wrap">
      <span data-testid={testId}>{open ? node.text : node.preview}</span>{' '}
      <button type="button" className="text-xs font-medium text-primary underline" aria-expanded={open} data-testid={`${testId}-more`} onClick={() => setOpen((v) => !v)}>
        {open ? 'Show less' : 'Show more'}
      </button>
    </span>
  );
}

/** "3 items" with the first few named after it; opens to one card per item. */
export function ListValue({
  node, testId, path, renderNode,
}: {
  node: Extract<HumanNode, { kind: 'list' }>;
  testId: string;
  /** Dotted path of this list in the data; each item's own rows continue from `<path>.<index>`. */
  path: string;
  renderNode: (n: HumanNode, path: string) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(LIST_PAGE);
  const word = node.count === 1 ? 'item' : 'items';
  return (
    <div data-testid={testId}>
      <button
        type="button"
        className="group flex w-full items-start gap-1 rounded text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        data-testid={`${testId}-toggle`}
      >
        <ChevronRight className={cn('mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform', open && 'rotate-90')} />
        <span className="min-w-0">
          <span className="font-medium" data-testid={`${testId}-count`}>{node.count} {word}</span>
          {!open && node.summary && <span className="text-muted-foreground"> · {node.summary}</span>}
        </span>
      </button>
      {open && (
        <ol className="mt-2 space-y-2" data-testid={`${testId}-items`}>
          {node.items.slice(0, shown).map((item: HumanItem) => (
            <li key={item.index} className="rounded-md border border-line bg-paper-deep/40 p-2" data-testid={`${testId}-item-${item.index}`}>
              {node.items.some((i) => i.body.kind === 'rows' || i.title !== `Item ${i.index + 1}`) && <div className="mb-1 text-sm font-medium">{item.title}</div>}
              {item.body.kind !== 'empty' && renderNode(item.body, path ? `${path}.${item.index}` : String(item.index))}
            </li>
          ))}
          {node.items.length > shown && (
            <li>
              <button type="button" className="text-xs font-medium text-primary underline" data-testid={`${testId}-show-more`} onClick={() => setShown((n) => n + LIST_PAGE)}>
                Show {Math.min(LIST_PAGE, node.items.length - shown)} more
              </button>
            </li>
          )}
        </ol>
      )}
    </div>
  );
}
