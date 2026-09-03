import { useState } from 'react';
import { Label } from './ui/label';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Button } from './ui/button';
import { VariablePicker } from './ui/VariablePicker';

/**
 * Minimal JSON Schema shape we care about. Real schemas (especially from MCP servers)
 * can contain arbitrary extra keys/constructs — we only read what we need and treat
 * everything else as "don't understand this, fall back to raw JSON".
 */
export type JSONSchema = Record<string, unknown>;

export interface JsonSchemaFormProps {
  /** JSON Schema describing the shape of `value`. `{}` / null / undefined means "unknown". */
  schema: JSONSchema | null | undefined;
  /** Current args object (or sub-object, when nested). */
  value: Record<string, unknown>;
  /** Called with the full replacement object whenever anything changes. */
  onChange: (next: Record<string, unknown>) => void;
  /** Disables the VariablePicker affordance for nested renders where it'd be noisy. */
  showVariablePicker?: boolean;
}

const PRIMITIVE_TYPES = new Set(['string', 'number', 'integer', 'boolean']);

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function isSchemaEmpty(schema: JSONSchema | null | undefined): boolean {
  if (!schema) return true;
  return Object.keys(schema).length === 0;
}

function hasEscapeHatchConstructs(schema: JSONSchema): boolean {
  return Boolean(
    schema.anyOf || schema.oneOf || schema.allOf || schema.$ref || schema.not
  );
}

type FieldTier = 'primitive' | 'enum-or-bool' | 'flat-object' | 'primitive-array' | 'raw';

function classifyField(schema: JSONSchema): FieldTier {
  if (isSchemaEmpty(schema) || hasEscapeHatchConstructs(schema)) return 'raw';

  if (Array.isArray(schema.enum)) return 'enum-or-bool';

  const type = schema.type as string | undefined;

  if (type === 'boolean') return 'enum-or-bool';
  if (type === 'string' || type === 'number' || type === 'integer') return 'primitive';

  if (type === 'object') {
    const props = asRecord(schema.properties);
    const propSchemas = Object.values(props) as JSONSchema[];
    const allFlat = propSchemas.every((p) => {
      const t = (p && (p as JSONSchema).type) as string | undefined;
      return PRIMITIVE_TYPES.has(t || '') || Array.isArray((p as JSONSchema).enum);
    });
    if (Object.keys(props).length > 0 && allFlat) return 'flat-object';
    return 'raw'; // nested/deep object -> escape hatch
  }

  if (type === 'array') {
    const items = schema.items as JSONSchema | undefined;
    const itemType = items?.type as string | undefined;
    if (items && (PRIMITIVE_TYPES.has(itemType || '') || Array.isArray(items.enum))) {
      return 'primitive-array';
    }
    return 'raw'; // array of objects / tuple / unknown items -> escape hatch
  }

  // No recognizable `type` at all (could be a bare description-only schema) -> raw
  return 'raw';
}

/** Raw JSON escape-hatch editor for a single value. Kept local state so the user can type
 * invalid-in-progress JSON without losing keystrokes; validated on blur only. */
function RawJsonField({
  value,
  onCommit,
  rows = 4,
}: {
  value: unknown;
  onCommit: (next: unknown) => void;
  rows?: number;
}) {
  const initial = (() => {
    try {
      return JSON.stringify(value ?? '', null, 2);
    } catch {
      return '';
    }
  })();
  return (
    <RawJsonEditor initial={initial} onCommit={onCommit} rows={rows} />
  );
}

function RawJsonEditor({
  initial,
  onCommit,
  rows,
}: {
  initial: string;
  onCommit: (next: unknown) => void;
  rows: number;
}) {
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string | null>(null);

  return (
    <div>
      <textarea
        className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-xs font-mono ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        style={{ minHeight: `${rows * 18}px` }}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          if (text.trim() === '') {
            setError(null);
            onCommit(undefined);
            return;
          }
          try {
            const parsed = JSON.parse(text);
            setError(null);
            onCommit(parsed);
          } catch {
            setError('Invalid JSON — value was not saved. Fix the syntax and click away again.');
          }
        }}
        spellCheck={false}
      />
      {error && <p className="text-[10px] text-destructive mt-1">{error}</p>}
    </div>
  );
}

function PrimitiveField({
  fieldKey,
  schema,
  required,
  value,
  onChange,
  showVariablePicker = true,
}: {
  fieldKey: string;
  schema: JSONSchema;
  required: boolean;
  value: unknown;
  onChange: (v: string) => void;
  showVariablePicker?: boolean;
}) {
  const description = typeof schema.description === 'string' ? schema.description : undefined;
  const stringValue = value === undefined || value === null ? '' : String(value);
  const defaultValue = schema.default !== undefined ? String(schema.default) : undefined;

  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <Label htmlFor={`arg-${fieldKey}`} className="text-xs font-medium">
          {fieldKey} {required ? <span className="text-destructive">*</span> : ''}
        </Label>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground font-mono">{String(schema.type || '')}</span>
          {showVariablePicker && (
            <VariablePicker
              onSelect={(v) => {
                const current = stringValue;
                onChange(current + (current.length && !current.endsWith(' ') ? ' ' : '') + v);
              }}
            />
          )}
        </div>
      </div>
      <Input
        id={`arg-${fieldKey}`}
        value={stringValue}
        onChange={(e) => onChange(e.target.value)}
        placeholder={description || defaultValue || `Enter ${fieldKey}...`}
        className="h-8 text-xs font-mono"
      />
      {description && <p className="text-[10px] text-muted-foreground mt-1">{description}</p>}
    </div>
  );
}

/** enum / boolean fields: a quick-pick Select, with a toggle to fall back to a free-text
 * field so `{{variable}}` templates remain typeable (a Select cannot hold arbitrary text). */
function PickOrTemplateField({
  fieldKey,
  schema,
  required,
  value,
  onChange,
}: {
  fieldKey: string;
  schema: JSONSchema;
  required: boolean;
  value: unknown;
  onChange: (v: string) => void;
}) {
  const description = typeof schema.description === 'string' ? schema.description : undefined;
  const options: string[] = Array.isArray(schema.enum)
    ? (schema.enum as unknown[]).map((v) => String(v))
    : ['true', 'false'];
  const stringValue = value === undefined || value === null ? '' : String(value);
  const looksLikeTemplate = stringValue.includes('{{');
  const [templateMode, setTemplateMode] = useState(looksLikeTemplate);

  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <Label htmlFor={`arg-${fieldKey}`} className="text-xs font-medium">
          {fieldKey} {required ? <span className="text-destructive">*</span> : ''}
        </Label>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground font-mono">{String(schema.type || 'enum')}</span>
          <Button
            type="button"
            variant="ghost"
            className="h-5 px-1 text-[10px]"
            onClick={() => setTemplateMode((m) => !m)}
          >
            {templateMode ? 'Use picker' : 'Use variable'}
          </Button>
        </div>
      </div>
      {templateMode ? (
        <Input
          id={`arg-${fieldKey}`}
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
          placeholder={description || 'e.g. {{SomeNodeResult}}'}
          className="h-8 text-xs font-mono"
        />
      ) : (
        <Select value={stringValue || undefined} onValueChange={onChange}>
          <SelectTrigger id={`arg-${fieldKey}`} className="h-8 text-xs">
            <SelectValue placeholder={`Select ${fieldKey}...`} />
          </SelectTrigger>
          <SelectContent>
            {options.map((opt) => (
              <SelectItem key={opt} value={opt}>{opt}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {description && <p className="text-[10px] text-muted-foreground mt-1">{description}</p>}
    </div>
  );
}

function PrimitiveArrayField({
  fieldKey,
  schema,
  value,
  onChange,
}: {
  fieldKey: string;
  schema: JSONSchema;
  value: unknown;
  onChange: (v: string[]) => void;
}) {
  const description = typeof schema.description === 'string' ? schema.description : undefined;
  const arr: string[] = Array.isArray(value) ? (value as unknown[]).map((v) => String(v)) : [];

  return (
    <div>
      <Label className="text-xs font-medium mb-1 block">{fieldKey}</Label>
      <div className="space-y-1">
        {arr.map((item, idx) => (
          <div key={idx} className="flex gap-1">
            <Input
              value={item}
              onChange={(e) => {
                const next = [...arr];
                next[idx] = e.target.value;
                onChange(next);
              }}
              className="h-8 text-xs font-mono"
              placeholder={`Item ${idx + 1}`}
            />
            <Button
              type="button"
              variant="ghost"
              className="h-8 px-2 text-xs"
              onClick={() => onChange(arr.filter((_, i) => i !== idx))}
            >
              Remove
            </Button>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          className="h-7 px-2 text-xs"
          onClick={() => onChange([...arr, ''])}
        >
          + Add item
        </Button>
      </div>
      {description && <p className="text-[10px] text-muted-foreground mt-1">{description}</p>}
    </div>
  );
}

export function JsonSchemaForm({ schema, value, onChange, showVariablePicker = true }: JsonSchemaFormProps) {
  const safeSchema = schema || {};

  // Unknown/empty schema for the whole object -> single raw JSON editor.
  const properties = asRecord(safeSchema.properties);
  if (isSchemaEmpty(safeSchema) || Object.keys(properties).length === 0) {
    return (
      <RawJsonField
        value={value}
        rows={6}
        onCommit={(next) => {
          if (next === undefined) return;
          if (next && typeof next === 'object' && !Array.isArray(next)) {
            onChange(next as Record<string, unknown>);
          }
        }}
      />
    );
  }

  const requiredList = Array.isArray(safeSchema.required) ? (safeSchema.required as string[]) : [];

  return (
    <div className="space-y-3">
      {Object.entries(properties).map(([key, rawPropSchema]) => {
        const propSchema = (rawPropSchema || {}) as JSONSchema;
        const required = requiredList.includes(key);
        const tier = classifyField(propSchema);
        const current = value?.[key];

        const setField = (v: unknown) => onChange({ ...value, [key]: v });

        if (tier === 'primitive') {
          return (
            <PrimitiveField
              key={key}
              fieldKey={key}
              schema={propSchema}
              required={required}
              value={current}
              onChange={setField}
              showVariablePicker={showVariablePicker}
            />
          );
        }

        if (tier === 'enum-or-bool') {
          return (
            <PickOrTemplateField
              key={key}
              fieldKey={key}
              schema={propSchema}
              required={required}
              value={current}
              onChange={setField}
            />
          );
        }

        if (tier === 'primitive-array') {
          return (
            <PrimitiveArrayField
              key={key}
              fieldKey={key}
              schema={propSchema}
              value={current}
              onChange={setField}
            />
          );
        }

        if (tier === 'flat-object') {
          return (
            <div key={key} className="border rounded-md p-2 bg-background/50">
              <Label className="text-xs font-medium mb-2 block">
                {key} {required ? <span className="text-destructive">*</span> : ''}
              </Label>
              <JsonSchemaForm
                schema={propSchema}
                value={asRecord(current)}
                onChange={(nested) => setField(nested)}
                showVariablePicker={showVariablePicker}
              />
            </div>
          );
        }

        // tier === 'raw': escape hatch for anyOf/oneOf/$ref/deep nesting/unrecognized schema.
        return (
          <div key={key}>
            <div className="flex justify-between items-center mb-1">
              <Label className="text-xs font-medium">
                {key} {required ? <span className="text-destructive">*</span> : ''}
              </Label>
              <span className="text-[10px] text-muted-foreground">raw JSON</span>
            </div>
            {typeof propSchema.description === 'string' && (
              <p className="text-[10px] text-muted-foreground mb-1">{propSchema.description}</p>
            )}
            <RawJsonField
              value={current !== undefined ? current : propSchema.default}
              onCommit={(next) => setField(next)}
            />
          </div>
        );
      })}
    </div>
  );
}
