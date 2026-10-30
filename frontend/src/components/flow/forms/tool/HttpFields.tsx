import { type ReactNode } from 'react';
import { Button } from '../../../ui/button';
import { JsonArea } from '@/components/common/JsonArea';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { isRowShaped, KeyValueRows } from '../fields';

const asText = (v: unknown): string => (typeof v === 'string' ? v : v === undefined || v === null ? '' : JSON.stringify(v, null, 2));

/**
 * Headers and the request body of an HTTP step. These really are JSON, so they live in a titled JSON area (Format, Copy,
 * a readable error, an example), with name / value rows first when the value is simple enough to show that way.
 * Half-typed JSON is kept as text so nothing is lost while typing; the area says what is wrong.
 */
export function HttpJsonField({
  surfaceKey, title, help, example, value, onChange, nodeId, rows,
}: {
  surfaceKey: string;
  title: string;
  help: ReactNode;
  /** Filled in by "Use an example" when the box is empty. */
  example: unknown;
  value: unknown;
  onChange: (next: unknown) => void;
  nodeId: string;
  rows: { keyLabel: string; valueLabel: string; keyPlaceholder: string; valuePlaceholder: string; addLabel: string };
}) {
  const { canManage } = useFlowPermissions();
  const text = asText(value);
  const edit = (next: string) => {
    if (next.trim() === '') return onChange(undefined);
    try {
      onChange(JSON.parse(next));
    } catch {
      onChange(next);
    }
  };
  const empty = text.trim() === '';
  return (
    <div className="space-y-1.5" data-testid={`flow-http-${surfaceKey}`}>
      <JsonArea
        surfaceKey={`http-${surfaceKey}`}
        title={title}
        help={help}
        value={text}
        onChange={canManage ? edit : undefined}
        readOnly={!canManage}
        allowEmpty
        placeholder={JSON.stringify(example, null, 2)}
        formView={
          isRowShaped(value) ? (
            <KeyValueRows value={value} onChange={onChange} nodeId={nodeId} testId={`flow-http-${surfaceKey}-rows`} disabled={!canManage} {...rows} />
          ) : undefined
        }
      />
      {empty && canManage && (
        <Button type="button" variant="ghost" size="sm" className="text-muted-foreground" data-testid={`flow-http-${surfaceKey}-example`} onClick={() => onChange(example)}>
          Use an example
        </Button>
      )}
    </div>
  );
}
