import { useEffect, useState } from 'react';
import { ChevronDownIcon, Sparkles } from 'lucide-react';
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
  ProcedureProposal,
  ProcedureProposalArgBinding,
  ProcedureProposalStep,
} from '@/services/procedureProposalApi';

interface ProposeProcedureDialogProps {
  agentRunName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function isArgBinding(value: unknown): value is ProcedureProposalArgBinding {
  return !!value && typeof value === 'object' && 'source' in (value as Record<string, unknown>);
}

/** One line describing how a step's argument was bound, e.g. "city: from input (city)". */
function describeArg(name: string, raw: unknown): string {
  if (isArgBinding(raw)) {
    if (raw.source === 'input') return `${name}: from input (${String(raw.value)})`;
    if (raw.source === 'step') return `${name}: from step "${String(raw.value)}"`;
    return `${name}: constant (${JSON.stringify(raw.value)})`;
  }
  return `${name}: ${JSON.stringify(raw)}`;
}

function stepLabel(step: ProcedureProposalStep, index: number): string {
  return step.tool || step.name || `Step ${index + 1}`;
}

function inputFieldList(inputSchema: ProcedureProposal['input_schema']): { name: string; type?: string; required?: boolean }[] {
  if (!inputSchema) return [];
  if (Array.isArray(inputSchema)) {
    return inputSchema.map((field) => ({ name: field.name, type: field.type, required: field.required }));
  }
  // Fallback: JSON-schema-like object with a `properties` map.
  const props = (inputSchema as Record<string, unknown>).properties as Record<string, { type?: string }> | undefined;
  if (props && typeof props === 'object') {
    const required = new Set(((inputSchema as Record<string, unknown>).required as string[] | undefined) ?? []);
    return Object.entries(props).map(([name, def]) => ({ name, type: def?.type, required: required.has(name) }));
  }
  return [];
}

/**
 * Review dialog for turning a completed Agent Run into a deterministic Procedure
 * (Run & Propose Procedure). Structured after ConvertToProcedureDialog.tsx's
 * "preview, then accept a Draft" shape: `propose_procedure_from_run` is a read-only
 * preview, `accept_procedure_proposal` is the only step that actually saves anything,
 * and it always creates a Draft the user still has to review and enable elsewhere.
 * This dialog is not a graph editor -- the compiled graph is shown read-only and
 * accepted unmodified; only the procedure's name is editable here.
 */
export function ProposeProcedureDialog({ agentRunName, open, onOpenChange }: ProposeProcedureDialogProps) {
  const [loading, setLoading] = useState(false);
  const [proposal, setProposal] = useState<ProcedureProposal | null>(null);
  const [name, setName] = useState('');
  const [accepting, setAccepting] = useState(false);
  const [accepted, setAccepted] = useState<{ name: string; procedure_id: string } | null>(null);
  const [rawOpen, setRawOpen] = useState(false);

  useEffect(() => {
    if (!open) {
      setProposal(null);
      setAccepted(null);
      setRawOpen(false);
      return;
    }
    setLoading(true);
    proposeProcedureFromRun(agentRunName)
      .then((result) => {
        setProposal(result);
        setName(`Procedure from run ${agentRunName}`);
      })
      .catch(() => setProposal(null))
      .finally(() => setLoading(false));
  }, [open, agentRunName]);

  const handleAccept = async () => {
    if (!proposal?.procedure_graph) return;
    setAccepting(true);
    try {
      const result = await acceptProcedureProposal(agentRunName, proposal.procedure_graph, name.trim());
      toast.success('Procedure created as a draft', {
        description: `Review "${result.procedure_id}" before enabling it.`,
      });
      setAccepted({ name: result.name, procedure_id: result.procedure_id });
    } catch {
      // handleFrappeError inside acceptProcedureProposal already surfaced this
    } finally {
      setAccepting(false);
    }
  };

  const steps = proposal?.procedure_graph?.steps ?? [];
  const inputFields = inputFieldList(proposal?.input_schema);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            Propose as procedure
          </DialogTitle>
          <DialogDescription>
            Turn this run into a fixed, deterministic procedure your agents can run directly.
          </DialogDescription>
        </DialogHeader>

        {loading && <div className="py-6 text-sm text-muted-foreground">Analyzing this run...</div>}

        {!loading && proposal && !proposal.proposable && (
          <div className="py-2 text-sm text-muted-foreground">
            {proposal.reason || "This run isn't a good fit for a deterministic procedure."}
          </div>
        )}

        {!loading && proposal && proposal.proposable && accepted && (
          <div className="py-2 space-y-2 text-sm">
            <p>
              Created as a Draft. It won&apos;t run anywhere until you review and enable it.
            </p>
            <Link
              to={`/procedures/${accepted.name}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline underline-offset-2"
            >
              View {accepted.procedure_id}
            </Link>
          </div>
        )}

        {!loading && proposal && proposal.proposable && !accepted && (
          <div className="space-y-4 py-2 text-sm">
            <div className="flex items-center gap-2">
              <label htmlFor="procedure-name" className="font-medium shrink-0">
                Name
              </label>
              <Input
                id="procedure-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Procedure name"
              />
            </div>

            <div className="text-muted-foreground">
              {proposal.step_count ?? steps.length} step{(proposal.step_count ?? steps.length) === 1 ? '' : 's'} detected
            </div>

            {inputFields.length > 0 && (
              <div>
                <div className="font-medium mb-1">Input fields</div>
                <div className="flex flex-wrap gap-1.5">
                  {inputFields.map((field) => (
                    <Badge key={field.name} variant="secondary" className="font-normal">
                      {field.name}
                      {field.type ? `: ${field.type}` : ''}
                      {field.required ? ' *' : ''}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {steps.length > 0 && (
              <div>
                <div className="font-medium mb-1">Compiled steps</div>
                <ol className="space-y-2">
                  {steps.map((step, index) => (
                    <li key={step.id ?? index} className="rounded-md border border-line p-2">
                      <div className="font-medium">
                        {index + 1}. {stepLabel(step, index)}
                      </div>
                      {step.args && Object.keys(step.args).length > 0 && (
                        <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                          {Object.entries(step.args).map(([argName, argValue]) => (
                            <li key={argName}>{describeArg(argName, argValue)}</li>
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
                  View raw graph
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <pre className="mt-1 max-h-48 overflow-auto rounded-md bg-muted p-2 text-[11px]">
                  {JSON.stringify(proposal.procedure_graph, null, 2)}
                </pre>
              </CollapsibleContent>
            </Collapsible>
          </div>
        )}

        <DialogFooter>
          {accepted ? (
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              {proposal?.proposable && (
                <Button onClick={handleAccept} disabled={accepting || !name.trim()}>
                  {accepting ? 'Creating draft...' : 'Accept & create draft'}
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
