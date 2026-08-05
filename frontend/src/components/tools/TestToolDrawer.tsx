import { useMemo, useState } from 'react';
import { FlaskConical, Play } from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { db } from '@/lib/frappe-sdk';

interface TestToolDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  toolName: string;
  types?: string;
  referenceDoctype?: string;
  functionDefinition: Record<string, unknown>;
}

interface ArgSpec {
  name: string;
  type: string;
  required: boolean;
  description?: string;
}

/** Verbs that can be executed live (read-only) straight from the drawer. */
const LIVE_EXECUTABLE_TYPES = new Set([
  'Get Document',
  'Get Multiple Documents',
  'Get List',
  'Get Amended Document',
]);

function extractArgSpecs(functionDefinition: Record<string, unknown>): ArgSpec[] {
  const params = functionDefinition?.parameters as
    | { properties?: Record<string, any>; required?: string[] }
    | undefined;
  if (!params?.properties) return [];
  const required = new Set(params.required || []);
  return Object.entries(params.properties).map(([name, spec]) => ({
    name,
    type: (spec?.type as string) || 'string',
    required: required.has(name),
    description: spec?.description as string | undefined,
  }));
}

export function TestToolDrawer({
  open,
  onOpenChange,
  toolName,
  types,
  referenceDoctype,
  functionDefinition,
}: TestToolDrawerProps) {
  const argSpecs = useMemo(() => extractArgSpecs(functionDefinition), [functionDefinition]);
  const [values, setValues] = useState<Record<string, string | boolean>>({});
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; payload: unknown; dryRun: boolean } | null>(
    null
  );

  const canRunLive = !!types && LIVE_EXECUTABLE_TYPES.has(types) && !!referenceDoctype;

  const setValue = (name: string, value: string | boolean) => {
    setValues((prev) => ({ ...prev, [name]: value }));
  };

  const parseArgs = (): { args: Record<string, unknown>; error?: string } => {
    const args: Record<string, unknown> = {};
    for (const spec of argSpecs) {
      const raw = values[spec.name];
      if (raw === undefined || raw === '') {
        if (spec.required) {
          return { args, error: `Missing required argument: ${spec.name}` };
        }
        continue;
      }
      if (spec.type === 'integer' || spec.type === 'number') {
        const num = Number(raw);
        if (Number.isNaN(num)) {
          return { args, error: `Argument "${spec.name}" must be a number.` };
        }
        args[spec.name] = num;
      } else if (spec.type === 'boolean') {
        args[spec.name] = raw === true || raw === 'true';
      } else if (spec.type === 'array' || spec.type === 'object') {
        try {
          args[spec.name] = JSON.parse(String(raw));
        } catch {
          return { args, error: `Argument "${spec.name}" must be valid JSON.` };
        }
      } else {
        args[spec.name] = raw;
      }
    }
    return { args };
  };

  const executeLive = async (args: Record<string, unknown>): Promise<unknown> => {
    const doctype = referenceDoctype as string;
    switch (types) {
      case 'Get Document': {
        if (!args.document_id) throw new Error('document_id is required for a live Get Document test.');
        return db.getDoc(doctype, String(args.document_id));
      }
      case 'Get Multiple Documents': {
        const ids = Array.isArray(args.document_ids) ? (args.document_ids as string[]) : [];
        if (ids.length === 0) throw new Error('document_ids must be a non-empty array.');
        return db.getDocList(doctype, {
          filters: [['name', 'in', ids]],
          limit: Math.max(ids.length, 20),
        });
      }
      case 'Get List': {
        const rawFilters = (args.filters || {}) as Record<string, unknown>;
        const filters = Object.entries(rawFilters).map(
          ([field, value]) => [field, '=', value] as [string, '=', any]
        );
        return db.getDocList(doctype, {
          filters,
          fields: Array.isArray(args.fields) ? (args.fields as string[]) : undefined,
          limit: typeof args.limit === 'number' && args.limit > 0 ? args.limit : 20,
        });
      }
      case 'Get Amended Document': {
        if (!args.document_id) throw new Error('document_id is required for a live test.');
        return db.getDocList(doctype, {
          filters: [['amended_from', '=', String(args.document_id)]],
          limit: 1,
        });
      }
      default:
        throw new Error('Live execution is not supported for this operation type.');
    }
  };

  const handleRun = async () => {
    const { args, error } = parseArgs();
    if (error) {
      setResult({ ok: false, payload: error, dryRun: false });
      return;
    }

    setRunning(true);
    setResult(null);
    try {
      if (canRunLive) {
        const data = await executeLive(args);
        setResult({ ok: true, payload: data, dryRun: false });
      } else {
        // Dry run: show exactly what would be sent without mutating data.
        setResult({
          ok: true,
          payload: {
            tool: toolName || 'untitled_tool',
            operation: types,
            reference_doctype: referenceDoctype,
            arguments: args,
          },
          dryRun: true,
        });
      }
    } catch (err: any) {
      setResult({
        ok: false,
        payload: err?.message || err?.response?.data?.message || String(err),
        dryRun: false,
      });
    } finally {
      setRunning(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <FlaskConical className="w-4 h-4" />
            Test call — {toolName || 'untitled_tool'}
          </SheetTitle>
          <SheetDescription>
            {canRunLive
              ? 'Read-only operation: this test runs live against your data.'
              : 'This operation can modify data, so the test performs a dry run and shows the payload that would be sent.'}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-4 mt-6">
          {!canRunLive && (
            <Alert>
              <AlertDescription>
                Dry run only. Save the tool and run it through an agent to execute write operations.
              </AlertDescription>
            </Alert>
          )}

          {argSpecs.length === 0 ? (
            <div className="text-sm text-steel border border-dashed rounded p-4 text-center">
              This tool takes no arguments.
            </div>
          ) : (
            <div className="space-y-4">
              {argSpecs.map((spec) => (
                <div key={spec.name} className="space-y-1.5">
                  <Label htmlFor={`test-arg-${spec.name}`} className="flex items-center gap-2">
                    <span className="font-mono text-sm">{spec.name}</span>
                    <Badge variant="outline" className="text-[10px]">
                      {spec.type}
                    </Badge>
                    {spec.required && <span className="text-destructive">*</span>}
                  </Label>
                  {spec.type === 'boolean' ? (
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id={`test-arg-${spec.name}`}
                        checked={values[spec.name] === true}
                        onCheckedChange={(checked) => setValue(spec.name, checked === true)}
                      />
                      <span className="text-sm text-steel">true</span>
                    </div>
                  ) : spec.type === 'array' || spec.type === 'object' ? (
                    <Textarea
                      id={`test-arg-${spec.name}`}
                      className="font-mono text-xs min-h-[80px]"
                      placeholder={spec.type === 'array' ? '["value1", "value2"]' : '{"key": "value"}'}
                      value={String(values[spec.name] ?? '')}
                      onChange={(e) => setValue(spec.name, e.target.value)}
                    />
                  ) : (
                    <Input
                      id={`test-arg-${spec.name}`}
                      type={spec.type === 'integer' || spec.type === 'number' ? 'number' : 'text'}
                      value={String(values[spec.name] ?? '')}
                      onChange={(e) => setValue(spec.name, e.target.value)}
                    />
                  )}
                  {spec.description && <p className="text-xs text-steel">{spec.description}</p>}
                </div>
              ))}
            </div>
          )}

          <Button type="button" onClick={handleRun} disabled={running} className="w-full">
            <Play className="w-4 h-4 mr-2" />
            {running ? 'Running...' : canRunLive ? 'Run test' : 'Dry run'}
          </Button>

          {result && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">
                  {result.dryRun ? 'Payload preview' : result.ok ? 'Result' : 'Error'}
                </span>
                <Badge variant={result.ok ? 'secondary' : 'destructive'} className="text-[10px]">
                  {result.dryRun ? 'dry run' : result.ok ? 'success' : 'failed'}
                </Badge>
              </div>
              <div className="rounded-lg border border-line bg-ink p-3 max-h-[40vh] overflow-auto">
                <pre className="text-xs font-mono text-steel-soft whitespace-pre-wrap">
                  {typeof result.payload === 'string'
                    ? result.payload
                    : JSON.stringify(result.payload, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
