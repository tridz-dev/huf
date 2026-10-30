import { Button } from '../../ui/button';
import { Label } from '../../ui/label';
import { JsonArea } from '@/components/common/JsonArea';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import type { DataInputProps } from './DataInput';

/** A value that is a list or an object is edited as JSON, in the one JSON area (never mixed into the friendly fields). */
export function JsonDataInput({ value, onChange, hint, testId, id, label, optional, placeholder, forced, onUseText }: DataInputProps & { forced: boolean; onUseText: () => void }) {
  const { canManage } = useFlowPermissions();
  const text = typeof value === 'string' ? value : value === undefined || value === null ? '' : JSON.stringify(value, null, 2);
  const key = (testId ?? id ?? 'value').replace(/[^a-z0-9]+/gi, '-').toLowerCase();

  const edit = (next: string) => {
    if (next.trim() === '') return onChange(undefined);
    try {
      onChange(JSON.parse(next));
    } catch {
      // Not valid yet: keep the words so nothing is lost, the area shows what is wrong.
      onChange(next);
    }
  };

  return (
    <div className="space-y-1" data-testid={testId ? `-box` : undefined}>
      {label ? <Label size="sm" className="block min-w-0 truncate">{label}{optional ? ' (optional)' : ''}</Label> : null}
      <JsonArea
        surfaceKey={key}
        title="Advanced (JSON)"
        help={hint ?? 'A list or a set of named values. Edit it here, or replace it with plain text.'}
        value={text}
        onChange={canManage ? edit : undefined}
        readOnly={!canManage}
        allowEmpty
        placeholder={placeholder ?? '{\n  "name": "Ada"\n}'}
        textTestId={testId}
      />
      {!forced && canManage ? (
        <Button type="button" variant="ghost" size="sm" className="text-muted-foreground" onClick={onUseText} data-testid={testId ? `${testId}-use-text` : undefined}>
          Use plain text instead
        </Button>
      ) : null}
    </div>
  );
}
