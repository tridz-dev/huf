import { useEffect, useMemo, useRef, useState } from 'react';
import { ListTree, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Combobox } from '@/components/ui/combobox';
import {
  getAgentProcedures,
  type AgentProcedureDoc,
} from '@/services/agentProcedureApi';
import {
  createAgentProcedureBinding,
  deleteAgentProcedureBinding,
  getAgentProcedureBindings,
  type AgentProcedureBindingDoc,
} from '@/services/agentProcedureBindingApi';

interface ProcedureBindingsTabProps {
  /** The Agent this tab manages bindings for. Bindings can't be created until the
   * Agent itself has been saved (needs a `name` to link against). */
  agentId?: string;
}

export function ProcedureBindingsTab({ agentId }: ProcedureBindingsTabProps) {
  const [bindings, setBindings] = useState<AgentProcedureBindingDoc[]>([]);
  const [allProcedures, setAllProcedures] = useState<AgentProcedureDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedProcedure, setSelectedProcedure] = useState('');
  const [adding, setAdding] = useState(false);
  const [removingName, setRemovingName] = useState<string | null>(null);
  const comboboxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!agentId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      const [boundRows, procedureList] = await Promise.all([
        getAgentProcedureBindings(agentId),
        getAgentProcedures({ limit: 500 }),
      ]);
      if (cancelled) return;
      setBindings(boundRows);
      setAllProcedures(procedureList.data);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  const boundProcedureIds = useMemo(() => new Set(bindings.map((b) => b.procedure)), [bindings]);

  // Binding is only allowed against a read-only ("Read" tier) Procedure — a write
  // Procedure must never appear as a selectable option, only as a disabled explainer.
  const eligibleOptions = useMemo(
    () =>
      allProcedures
        .filter((p) => p.is_read_only && !boundProcedureIds.has(p.name))
        .map((p) => ({
          value: p.name,
          label: p.procedure_name || p.name,
          subtitle: `${p.tier || 'Draft'} · v${p.version ?? 1}`,
        })),
    [allProcedures, boundProcedureIds]
  );

  const disabledWriteProcedures = useMemo(
    () => allProcedures.filter((p) => !p.is_read_only && !boundProcedureIds.has(p.name)),
    [allProcedures, boundProcedureIds]
  );

  const procedureLabel = (procedureName: string) =>
    allProcedures.find((p) => p.name === procedureName)?.procedure_name || procedureName;

  const handleAdd = async () => {
    if (!agentId || !selectedProcedure) return;
    setAdding(true);
    try {
      const created = await createAgentProcedureBinding({ agent: agentId, procedure: selectedProcedure });
      if (created) {
        setBindings((prev) => [...prev, created]);
        toast.success('Procedure bound');
      }
      setSelectedProcedure('');
    } catch (err) {
      toast.error('Failed to bind procedure', {
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (binding: AgentProcedureBindingDoc) => {
    setRemovingName(binding.name);
    try {
      await deleteAgentProcedureBinding(binding.name);
      setBindings((prev) => prev.filter((b) => b.name !== binding.name));
      toast.success('Binding removed');
    } catch (err) {
      toast.error('Failed to remove binding', {
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    } finally {
      setRemovingName(null);
    }
  };

  if (!agentId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ListTree className="w-5 h-5" />
            Procedure bindings
          </CardTitle>
          <CardDescription>Save this agent first, then bind Procedures it can execute.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <ListTree className="w-5 h-5" />
              Procedure bindings
            </CardTitle>
            <CardDescription>
              Bind a saved Procedure to this agent so it can run those steps directly, instead of
              working out what to do from scratch every time. Only read-only procedures can be bound
              here — a write procedure needs approval first (see its detail page).
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-end gap-2" ref={comboboxRef}>
          <div className="flex-1">
            <Combobox
              options={eligibleOptions}
              value={selectedProcedure}
              onValueChange={setSelectedProcedure}
              placeholder="Select a read-only procedure..."
              searchPlaceholder="Search procedures..."
              emptyText="No eligible read-only procedures"
              disabled={loading}
            />
          </div>
          <Button type="button" size="sm" variant="outline" onClick={handleAdd} disabled={!selectedProcedure || adding}>
            <Plus className="w-4 h-4 mr-2" />
            Bind procedure
          </Button>
        </div>

        {disabledWriteProcedures.length > 0 && (
          <p className="text-xs text-muted-foreground">
            {disabledWriteProcedures.length} write-tier procedure
            {disabledWriteProcedures.length === 1 ? '' : 's'} hidden from this picker — binding is only
            allowed for read-only procedures.
          </p>
        )}

        {loading ? (
          <div className="text-sm font-body text-steel-soft py-6 text-center">Loading bindings...</div>
        ) : bindings.length === 0 ? (
          <div className="text-center py-12 border border-dashed rounded-lg bg-muted/20">
            <p className="text-muted-foreground mb-2">No procedures bound yet.</p>
            <p className="text-xs text-muted-foreground">
              Bind a saved procedure so this agent can just run it, instead of deciding the steps again
              every time.
            </p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {bindings.map((binding) => (
              <div
                key={binding.name}
                className="flex items-start justify-between gap-3 rounded-lg border p-4 hover:bg-muted/50 transition-colors"
              >
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="font-medium text-sm truncate">{procedureLabel(binding.procedure)}</h4>
                    <Badge variant={binding.enabled ? 'default' : 'secondary'} className="text-[10px] uppercase shrink-0">
                      {binding.enabled ? 'Enabled' : 'Disabled'}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground font-mono truncate">{binding.procedure}</p>
                  {binding.health && binding.health !== 'Unknown' && (
                    <Badge variant="outline" className="text-[10px]">
                      {binding.health}
                    </Badge>
                  )}
                </div>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  onClick={() => handleRemove(binding)}
                  disabled={removingName === binding.name}
                  aria-label="Remove binding"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
