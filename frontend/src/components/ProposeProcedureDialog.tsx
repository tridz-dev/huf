import { useCallback, useEffect, useState } from 'react';
import { ChevronDownIcon, Workflow } from 'lucide-react';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import {
  acceptProcedureProposal,
  proposeProcedureFromRun,
  ProcedureGraphRef,
  ProcedureProposal,
  ProcedureProposalNode,
} from '@/services/procedureProposalApi';

interface ProposeProcedureDialogProps {
  agentRunName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** A compiled tool step, flattened for display. */
interface DisplayStep {
  id: string;
  index: number;
  label: string;
  args: Record<string, unknown>;
}

function isRef(value: unknown): value is ProcedureGraphRef {
  return !!value && typeof value === 'object' && typeof (value as ProcedureGraphRef).$from === 'string';
}

/** "erpnext.create_sales_invoice" -> "Create sales invoice", so the review list reads as
 * actions rather than as tool identifiers. */
function humanizeTool(toolId: string): string {
  const tail = toolId.split(/[./]/).filter(Boolean).pop() ?? toolId;
  const words = tail.replace(/[_-]+/g, ' ').replace(/([a-z0-9])([A-Z])/g, '$1 $2').trim().toLowerCase();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : toolId;
}

/** The graph's tool.call nodes, in execution order, with the output node dropped. */
function displaySteps(graph: ProcedureProposal['procedure_graph']): DisplayStep[] {
  const nodes = (graph?.nodes ?? []) as ProcedureProposalNode[];
  return nodes
    .filter((node) => node?.type === 'tool.call')
    .map((node, index) => ({
      id: node.id ?? `step-${index}`,
      index: index + 1,
      label: humanizeTool(String(node.config?.tool_id ?? node.id ?? `Step ${index + 1}`)),
      args: (node.config?.input ?? {}) as Record<string, unknown>,
    }));
}

/** One plain-English line for how a step's argument gets its value when the procedure is
 * run later: supplied by whoever runs it, carried over from an earlier step, or fixed. */
function describeArg(name: string, raw: unknown, stepsById: Map<string, DisplayStep>): string {
  if (isRef(raw)) {
    if (raw.$from.startsWith('input.')) {
      return `${name}: you fill this in each time (${raw.$from.slice('input.'.length)})`;
    }
    const source = stepsById.get(raw.$from);
    return source
      ? `${name}: comes from step ${source.index} (${source.label})`
      : `${name}: comes from an earlier step`;
  }
  return `${name}: always ${JSON.stringify(raw)}`;
}

function inputFieldList(inputSchema: ProcedureProposal['input_schema']): { name: string; type?: string; required?: boolean }[] {
  if (!inputSchema) return [];
  if (Array.isArray(inputSchema)) {
    return inputSchema.map((field) => ({ name: field.name, type: field.type, required: field.required }));
  }
  // JSON-schema object with a `properties` map -- what the backend actually returns.
  const props = (inputSchema as Record<string, unknown>).properties as Record<string, { type?: string }> | undefined;
  if (props && typeof props === 'object') {
    const required = new Set(((inputSchema as Record<string, unknown>).required as string[] | undefined) ?? []);
    return Object.entries(props).map(([name, def]) => ({ name, type: def?.type, required: required.has(name) }));
  }
  return [];
}

/** Default name the user can overwrite. Built from what the run actually did, because the
 * Agent Run's docname is an opaque hash and makes a useless procedure name. */
function suggestName(steps: DisplayStep[]): string {
  if (steps.length === 0) return '';
  const rest = steps.length - 1;
  return rest > 0 ? `${steps[0].label} + ${rest} more step${rest === 1 ? '' : 's'}` : steps[0].label;
}

/**
 * Review dialog for saving a completed Agent Run's tool calls as a reusable Procedure
 * (Run & Propose Procedure). Structured after ConvertToProcedureDialog.tsx's
 * "preview, then accept a Draft" shape: `propose_procedure_from_run` is a read-only
 * preview, `accept_procedure_proposal` is the only step that actually saves anything,
 * and it always creates a Draft the user still has to review and enable elsewhere.
 * This dialog is not a graph editor -- the compiled graph is shown read-only and
 * accepted unmodified; only the procedure's name is editable here.
 */
export function ProposeProcedureDialog({ agentRunName, open, onOpenChange }: ProposeProcedureDialogProps) {
  const [loading, setLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [proposal, setProposal] = useState<ProcedureProposal | null>(null);
  const [name, setName] = useState('');
  const [accepting, setAccepting] = useState(false);
  const [accepted, setAccepted] = useState<{ name: string; procedure_id: string; label: string } | null>(null);
  const [rawOpen, setRawOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setLoadFailed(false);
    proposeProcedureFromRun(agentRunName)
      .then((result) => {
        setProposal(result);
        setName(suggestName(displaySteps(result.procedure_graph)));
      })
      .catch(() => {
        setProposal(null);
        setLoadFailed(true);
      })
      .finally(() => setLoading(false));
  }, [agentRunName]);

  useEffect(() => {
    if (!open) {
      setProposal(null);
      setAccepted(null);
      setRawOpen(false);
      setLoadFailed(false);
      return;
    }
    load();
  }, [open, load]);

  const handleAccept = async () => {
    if (!proposal?.procedure_graph) return;
    const label = name.trim();
    setAccepting(true);
    try {
      const result = await acceptProcedureProposal(agentRunName, proposal.procedure_graph, label);
      toast.success(`"${label}" saved as a draft procedure`, {
        description: 'Nothing runs it yet -- open it to review and turn it on.',
      });
      setAccepted({ name: result.name, procedure_id: result.procedure_id, label });
    } catch {
      // handleFrappeError inside acceptProcedureProposal already surfaced this
    } finally {
      setAccepting(false);
    }
  };

  const steps = displaySteps(proposal?.procedure_graph);
  const stepsById = new Map(steps.map((step) => [step.id, step]));
  const inputFields = inputFieldList(proposal?.input_schema);
  const stepCount = proposal?.step_count ?? steps.length;
  const sourceRun = proposal?.source_run ?? agentRunName;

  const sourceLine = (
    <div className="text-xs text-muted-foreground">
      Built from{' '}
      <Link
        to={`/executions/${sourceRun}`}
        target="_blank"
        rel="noopener noreferrer"
        className="underline underline-offset-2"
      >
        this answer&apos;s run ({sourceRun})
      </Link>
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Workflow className="w-4 h-4 text-primary" />
            Save these steps as a procedure
          </DialogTitle>
          <DialogDescription>
            A procedure repeats exactly the steps this answer took, in the same order, without
            the agent deciding anything again -- so it runs faster and the same way every time.
          </DialogDescription>
        </DialogHeader>

        {loading && <div className="py-6 text-sm text-muted-foreground">Checking what this answer did...</div>}

        {!loading && loadFailed && (
          <div className="space-y-2 py-2 text-sm">
            <p>We couldn&apos;t check this answer just now. Nothing was saved or changed.</p>
            <Button type="button" variant="outline" size="sm" onClick={load}>
              Try again
            </Button>
          </div>
        )}

        {!loading && proposal && !proposal.proposable && (
          <div className="space-y-2 py-2 text-sm">
            <p className="font-medium">These steps can&apos;t be saved as a procedure.</p>
            <p className="text-muted-foreground">
              {proposal.reason || 'This answer relied on judgement that would not repeat the same way.'}
            </p>
            <p className="text-muted-foreground">
              Nothing was saved or changed. Procedures only work when every step is repeatable
              with the same inputs -- ask the agent to redo this in clearer steps and try again.
            </p>
            {sourceLine}
          </div>
        )}

        {!loading && proposal && proposal.proposable && accepted && (
          <div className="py-2 space-y-2 text-sm">
            <p>
              <span className="font-medium">{accepted.label}</span> is saved as a draft procedure.
              Nothing runs it yet -- open it to review the steps and turn it on.
            </p>
            <Link
              to={`/procedures/${accepted.name}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline underline-offset-2"
            >
              Open it under Procedures
            </Link>
            <p className="text-xs text-muted-foreground">Reference: {accepted.procedure_id}</p>
          </div>
        )}

        {!loading && proposal && proposal.proposable && !accepted && (
          <div className="space-y-4 py-2 text-sm">
            {sourceLine}

            <div className="space-y-1.5">
              <label htmlFor="procedure-name" className="font-medium">
                Name it
              </label>
              <Input
                id="procedure-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Draft weekly invoice"
              />
              <p className="text-xs text-muted-foreground">
                You&apos;ll find it under this name in Procedures.
              </p>
            </div>

            <div className="text-muted-foreground">
              {stepCount} step{stepCount === 1 ? '' : 's'} will be saved
            </div>

            {inputFields.length > 0 && (
              <div>
                <div className="font-medium mb-1">You&apos;ll be asked for</div>
                <div className="flex flex-wrap gap-1.5">
                  {inputFields.map((field) => (
                    <Badge key={field.name} variant="secondary" className="font-normal">
                      {field.name}
                      {field.type ? `: ${field.type}` : ''}
                      {field.required ? ' *' : ''}
                    </Badge>
                  ))}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  These change each time you run it -- everything else stays fixed.
                </p>
              </div>
            )}

            {steps.length > 0 && (
              <div>
                <div className="font-medium mb-1">What it will do, every time</div>
                <ol className="space-y-2">
                  {steps.map((step) => (
                    <li key={step.id} className="rounded-md border border-line p-2">
                      <div className="font-medium">
                        {step.index}. {step.label}
                      </div>
                      {Object.keys(step.args).length > 0 && (
                        <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                          {Object.entries(step.args).map(([argName, argValue]) => (
                            <li key={argName}>{describeArg(argName, argValue, stepsById)}</li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            <Collapsible open={rawOpen} onOpenChange={setRawOpen}>
              <CollapsibleTrigger asChild>
                <Button type="button" variant="ghost" size="sm" className="h-7 px-2 -ml-2 text-xs text-muted-foreground">
                  <ChevronDownIcon className={`h-3.5 w-3.5 mr-1 transition-transform ${rawOpen ? 'rotate-180' : ''}`} />
                  View technical details
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <pre className="mt-1 max-h-48 overflow-auto rounded-md bg-muted p-2 text-[11px]">
                  {JSON.stringify(proposal.procedure_graph, null, 2)}
                </pre>
              </CollapsibleContent>
            </Collapsible>

            <p className="text-xs text-muted-foreground">
              Nothing has been saved yet. Creating the draft saves it under Procedures; it stays
              switched off until you review and enable it.
            </p>
          </div>
        )}

        <DialogFooter>
          {accepted ? (
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          ) : proposal?.proposable ? (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button onClick={handleAccept} disabled={accepting || !name.trim()}>
                {accepting ? 'Creating draft...' : 'Create draft procedure'}
              </Button>
            </>
          ) : (
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
