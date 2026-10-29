import { useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { humanize, type HumanNode, type HumanOptions } from '@/lib/flow-run/humanize';
import { JsonArea } from '@/components/common/JsonArea';
import { ListValue, LongText } from '@/components/common/HumanValueParts';

/**
 * Any run data, shown the way a person reads it (UX-2): labelled rows for objects, "N items" that open to one
 * card per item for lists, local friendly dates, Yes / No, empty values hidden, long text folded, step ids as
 * step titles. The exact data stays one click away behind "{ } Raw".
 *
 * Test ids (base `testId`, default `flow-human`): `<base>` root, `<base>-row-<path>` / `-label-<path>` /
 * `-value-<path>`, `<base>-list-<path>` (+ `-toggle`, `-count`, `-items`, `-item-N`), `<base>-text-<path>` (+ `-more`),
 * `<base>-empty`, `<base>-raw-toggle`, `<base>-raw` (the JSON area).
 */

export interface HumanValueProps extends HumanOptions {
  value: unknown;
  testId?: string;
  /** Offer a "{ } Raw" control that shows the exact data. `value` unless `rawValue` is given (e.g. secrets removed). */
  raw?: boolean;
  rawValue?: unknown;
  /** Title of the raw area. */
  rawTitle?: string;
  /** Test id wrapped around the raw JSON text (keeps older ids such as `flow-run-step-output-<id>` on the data). */
  rawTextTestId?: string;
  /** Shown when there is nothing worth showing. */
  emptyText?: string;
  className?: string;
}

function NodeView({ node, root, path }: { node: HumanNode; root: string; path: string }): ReactNode {
  const at = path ? `-${path}` : '';
  switch (node.kind) {
    case 'empty':
      return null;
    case 'scalar':
      return <span className="break-words" data-testid={`${root}-scalar${at}`}>{node.text}</span>;
    case 'text':
      return <LongText node={node} testId={`${root}-text${at}`} />;
    case 'list':
      return <ListValue node={node} testId={`${root}-list${at}`} path={path} renderNode={(n, p) => <NodeView node={n} root={root} path={p} />} />;
    case 'rows':
      return (
        <dl className="grid grid-cols-[minmax(0,max-content)_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm" data-testid={`${root}-rows${at}`}>
          {node.rows.map((r) => {
            const nested = r.node.kind === 'rows' || r.node.kind === 'list';
            return (
              <div key={r.path} className="contents" data-testid={`${root}-row-${r.path}`}>
                <dt className="max-w-[9rem] pt-0.5 text-xs text-muted-foreground break-words sm:max-w-[12rem]" data-testid={`${root}-label-${r.path}`}>{r.label}</dt>
                <dd className={cn('min-w-0', nested && r.node.kind === 'rows' && 'border-l border-line pl-3')} data-testid={`${root}-value-${r.path}`}>
                  <NodeView node={r.node} root={root} path={r.path} />
                </dd>
              </div>
            );
          })}
        </dl>
      );
  }
}

export function HumanValue({ value, testId = 'flow-human', raw = false, rawValue, rawTitle = 'Raw data', rawTextTestId, emptyText, className, ...opts }: HumanValueProps) {
  const [showRaw, setShowRaw] = useState(false);
  const node = humanize(value, opts);
  const rawData = rawValue === undefined ? value : rawValue;
  return (
    <div className={cn('space-y-2', className)} data-testid={testId}>
      {node.kind === 'empty' ? (
        emptyText ? <p className="text-xs text-muted-foreground" data-testid={`${testId}-empty`}>{emptyText}</p> : null
      ) : (
        <NodeView node={node} root={testId} path="" />
      )}
      {raw && (
        <div>
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            aria-expanded={showRaw}
            onClick={() => setShowRaw((v) => !v)}
            data-testid={`${testId}-raw-toggle`}
          >
            <span className="font-mono">{'{ }'}</span> {showRaw ? 'Hide raw' : 'Raw'}
          </button>
          {showRaw && (
            <JsonArea
              className="mt-2"
              surfaceKey={`${testId}-raw`}
              title={rawTitle}
              help="The exact data, as it was recorded. Nothing here can be edited."
              value={typeof rawData === 'string' ? rawData : JSON.stringify(rawData ?? null, null, 2)}
              readOnly
              textTestId={rawTextTestId}
            />
          )}
        </div>
      )}
    </div>
  );
}
