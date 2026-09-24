import { useMemo, useState, useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Combobox } from '@/components/ui/combobox';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Info } from 'lucide-react';
import { db } from '@/lib/frappe-sdk';
import type { BindingStats } from '@/services/decisionApi';

/**
 * Agent Decision Binding row from child table
 */
export interface AgentDecisionBindingRow {
  name?: string;
  surface: string;
  policy: string;
  mode: 'Off' | 'Shadow' | 'Advise' | 'Enforce';
  latency_budget_ms?: number;
  priority?: number;
  enabled?: 0 | 1;
}

/**
 * Surfaces where Advise mode is available (not offered for other surfaces)
 */
const ADVISE_SURFACES = new Set([
  'Tool Selection',
  'Skill Selection',
  'Procedure Selection',
  'Agent Routing',
  'RAG Filter',
]);

/**
 * Mode help text (plain language explanation)
 */
const MODE_HELP: Record<string, string> = {
  Off: 'Not used. This binding is inactive.',
  Shadow: 'Runs in the background and is only logged, the Agent never sees it. Use to test a policy before enabling.',
  Advise: 'The Agent sees a labelled suggestion with scores and still chooses freely. Nothing is narrowed.',
  Enforce: 'The result is applied and the Agent follows it. Falls back to normal behavior on timeout or failure.',
};

/**
 * Surface help text (what the surface decides)
 */
const SURFACE_HELP: Record<string, string> = {
  'Tool Selection': 'Decides which tools to show the Agent.',
  'Skill Selection': 'Decides which skills to make available.',
  'Procedure Selection': 'Decides which procedures to expose.',
  'Model Routing': 'Decides which model to use for this conversation.',
  'Agent Routing': 'Decides which Agent to route to (Hub Orchestrator only).',
  'RAG Filter': 'Decides which knowledge to include in context.',
  'Context Relevance': 'Decides which conversation history is relevant.',
  'Input Guardrail': 'Judges input before processing.',
  'Output Guardrail': 'Judges output before sending to user.',
  'Output Verification': 'Verifies output quality.',
  'Agent Tool': 'Advisory result of the `decide` tool. User controls via tool policy list.',
};

interface DecisionBindingControlProps {
  /**
   * Surface name this control manages
   */
  surface: string;
  /**
   * Current binding row for this surface, undefined if not set
   */
  value: AgentDecisionBindingRow | undefined;
  /**
   * Called when binding changes (including deletions)
   */
  onChange: (value: AgentDecisionBindingRow | undefined) => void;
  /**
   * Stats for this binding (read-only display)
   */
  stats?: BindingStats;
  /**
   * Hide this control (site switch off or user lacks decision.run)
   */
  disabled?: boolean;
}

export function DecisionBindingControl({
  surface,
  value,
  onChange,
  stats,
  disabled = false,
}: DecisionBindingControlProps) {
  const [policyOptions, setPolicyOptions] = useState<Array<{ value: string; label: string }>>([]);

  // Load available policies on mount
  useEffect(() => {
    db.getDocList('Decision Policy', {
      fields: ['name'],
      limit: 500,
    })
      .then((policies: Array<{ name: string }>) => {
        setPolicyOptions(
          policies.map((p) => ({
            value: p.name,
            label: p.name,
          }))
        );
      })
      .catch((error: Error) => {
        console.error('Error loading policies:', error);
      });
  }, []);

  if (disabled) {
    return null;
  }

  const isAdviseApplicable = ADVISE_SURFACES.has(surface);
  const modeOptions = isAdviseApplicable
    ? ['Off', 'Shadow', 'Advise', 'Enforce']
    : ['Off', 'Shadow', 'Enforce'];

  // Format stats summary: "212 calls, followed advice 78%, fallback 2%, $0.01"
  const statsSummary = useMemo(() => {
    if (!stats) return null;
    const parts: string[] = [];
    if (stats.stats.calls > 0) {
      parts.push(`${stats.stats.calls} calls`);
    }
    if (value?.mode === 'Advise' && stats.stats.advise_followed_rate !== null) {
      parts.push(`followed advice ${Math.round(stats.stats.advise_followed_rate * 100)}%`);
    }
    if (value?.mode === 'Shadow' && stats.stats.shadow_agreement !== null) {
      parts.push(`agreement ${Math.round(stats.stats.shadow_agreement * 100)}%`);
    }
    if (stats.stats.fallback_rate > 0) {
      parts.push(`fallback ${Math.round(stats.stats.fallback_rate * 100)}%`);
    }
    if (stats.stats.calls > 0) {
      // Rough cost estimate (would need actual spend per call in production)
      parts.push('$0.00');
    }
    return parts.length > 0 ? parts.join(', ') : null;
  }, [stats, value?.mode]);

  const handleModeChange = (newMode: string) => {
    if (!value) {
      // Create new binding with Off mode
      onChange({
        surface,
        policy: '',
        mode: newMode as 'Off' | 'Shadow' | 'Advise' | 'Enforce',
        enabled: 1,
      });
    } else {
      onChange({
        ...value,
        mode: newMode as 'Off' | 'Shadow' | 'Advise' | 'Enforce',
      });
    }
  };

  const handlePolicyChange = (policy: string) => {
    if (policy === '') {
      // Delete the binding
      onChange(undefined);
    } else {
      onChange({
        ...(value || { surface, mode: 'Off' as const, enabled: 1 }),
        policy,
      });
    }
  };

  const handleLatencyChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const latency = e.target.value ? parseInt(e.target.value, 10) : undefined;
    if (!value) {
      onChange({
        surface,
        policy: '',
        mode: 'Off',
        latency_budget_ms: latency,
        enabled: 1,
      });
    } else {
      onChange({
        ...value,
        latency_budget_ms: latency,
      });
    }
  };

  return (
    <div className="space-y-3 border-t pt-3">
      <div className="flex items-center justify-between">
        <h4 className="font-medium text-sm">{surface}</h4>
        {stats && statsSummary && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-xs text-muted-foreground cursor-help flex items-center gap-1">
                  Last 7 days: {statsSummary}
                  <Info className="w-3 h-3" />
                </span>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs">Statistics are for information only.</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>

      <div className="space-y-2 pl-0">
        <div className="grid gap-2">
          <label className="text-sm font-medium">Policy</label>
          <Combobox
            options={policyOptions}
            value={value?.policy || ''}
            onValueChange={handlePolicyChange}
            placeholder="Select a policy..."
            searchPlaceholder="Search policies..."
            emptyText="No policies found"
          />
          <p className="text-xs text-muted-foreground">
            {SURFACE_HELP[surface] || 'Decides on this surface.'}
          </p>
        </div>

        <div className="grid gap-2">
          <label className="text-sm font-medium">Mode</label>
          <div className="flex gap-2">
            {modeOptions.map((mode) => (
              <TooltipProvider key={mode}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => handleModeChange(mode)}
                      className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                        value?.mode === mode
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted text-muted-foreground hover:bg-muted/80'
                      }`}
                    >
                      {mode}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="max-w-xs">{MODE_HELP[mode]}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            ))}
          </div>
          {value?.mode && MODE_HELP[value.mode] && (
            <p className="text-xs text-muted-foreground italic">
              {MODE_HELP[value.mode]}
            </p>
          )}
        </div>

        {value?.mode !== 'Off' && (
          <div className="grid gap-2">
            <label className="text-sm font-medium">
              Latency Budget (ms)
              <span className="font-normal text-muted-foreground ml-1">(optional override)</span>
            </label>
            <Input
              type="number"
              value={value?.latency_budget_ms ?? ''}
              onChange={handleLatencyChange}
              placeholder="e.g., 2000"
              min="0"
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Leave blank to use surface default. Decision calls fall back on timeout.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
