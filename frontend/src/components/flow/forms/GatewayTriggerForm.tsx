import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { Button } from '../../ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '../../ui/collapsible';
import { FieldHint } from '../FieldHint';
import { GatewayChooser } from '../triggers/GatewayChooser';
import { GatewayParamField } from '../triggers/GatewayParamField';
import { TRIGGER_NOTES } from '../triggers/triggerNotes';
import { useGatewayRegistry } from '@/hooks/flow/useGatewayRegistry';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { GATEWAY_TRIGGER_KINDS } from '@/lib/flow-gateway/triggerKinds';
import { hasCustomValue, paramValue, visibleParams, withParam } from '@/lib/flow-gateway/gatewayParams';
import { gatewaySubtitle } from '@/lib/flow-gateway/gatewaySummary';
import type { GatewayParam, GatewayParamSpec, GatewayParamValue } from '@/lib/flow-gateway/gatewayTrigger.types';
import type { GatewayKindId } from '@/lib/flow-gateway/gatewayWords';
import { str, useNodeForm } from './formKit';

/**
 * The Setup tab of a chat trigger ("When someone messages ..."): the number or bot first, then the options the server
 * describes for it, with the rarely used ones folded under "More options". One renderer serves the generic, WhatsApp
 * and Telegram triggers; only `kind` differs.
 */
export function GatewayTriggerForm({ nodeId, kind }: { nodeId: string; kind: GatewayKindId }) {
  const { cfg, patch, shell } = useNodeForm(nodeId, 'triggerConfig');
  const { canManage } = useFlowPermissions();
  const { registry, loading, failed, reload } = useGatewayRegistry();
  const nodeType = GATEWAY_TRIGGER_KINDS.find((k) => k.id === kind)!.nodeType;
  const spec = registry?.specs[nodeType];
  const params: GatewayParam[] = Array.isArray(cfg.params) ? (cfg.params as GatewayParam[]) : [];
  const gateway = str(cfg.gateway);
  const [moreOpen, setMoreOpen] = useState<boolean | null>(null);

  const setParam = (p: GatewayParamSpec, value: GatewayParamValue) => {
    const next = withParam(params, p, value);
    patch({ params: next.length ? next : undefined });
  };
  const field = (p: GatewayParamSpec) => (
    <GatewayParamField
      key={p.key}
      spec={p}
      value={paramValue(params, p)}
      onChange={(v) => setParam(p, v)}
      error={canManage ? shell.error(`params.${p.key}`) : undefined}
      disabled={!canManage}
    />
  );

  const setup = spec ? visibleParams(spec, params, 'setup') : [];
  const more = spec ? visibleParams(spec, params, 'more') : [];
  const moreHasValue = more.some((p) => hasCustomValue(params, p));
  const moreShown = moreOpen ?? moreHasValue;

  return (
    <div className="space-y-4" data-testid={`flow-gateway-trigger-${kind}`}>
      <p className="text-xs text-muted-foreground" data-testid="flow-hint-gateway-intro">
        Starts the flow when someone sends a message. What they wrote, who sent it and any files are available to the steps that follow.
      </p>

      {registry ? (
        <div>
          <GatewayChooser kind={kind} value={gateway} gateways={registry.gateways} disabled={!canManage} onChange={(name) => patch({ gateway: name })} />
          <shell.Err field="gateway" />
        </div>
      ) : failed ? (
        <div className="space-y-2" role="alert" data-testid="flow-gateway-load-failed">
          <p className="text-sm text-destructive">Could not load your channels.</p>
          <Button type="button" size="sm" variant="outline" onClick={reload} data-testid="flow-gateway-retry">Try again</Button>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground" data-testid="flow-gateway-loading">{loading ? 'Loading your channels…' : ''}</p>
      )}

      {registry ? (
        <p className="rounded-md bg-muted/50 px-2.5 py-2 text-sm" data-testid="flow-gateway-filter-summary">
          {gatewaySubtitle(kind, { gateway, params }, registry.gateways)}
        </p>
      ) : null}

      {spec ? (
        <>
          <div className="space-y-4" data-testid="flow-gateway-options">
            <div>
              <h4 className="text-sm font-medium">Only start for some messages</h4>
              <FieldHint testId="flow-hint-gateway-narrow">Leave everything empty to start for every message. This can only narrow what the channel already lets in.</FieldHint>
            </div>
            {setup.map(field)}
          </div>
          {more.length > 0 ? (
            <Collapsible open={moreShown} onOpenChange={setMoreOpen} data-testid="flow-gateway-more">
              <CollapsibleTrigger className="flex items-center gap-1 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" data-testid="flow-gateway-more-toggle">
                <ChevronRight className={`h-4 w-4 transition-transform ${moreShown ? 'rotate-90' : ''}`} aria-hidden />
                More options
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-3 space-y-4" data-testid="flow-gateway-more-body">{more.map(field)}</CollapsibleContent>
            </Collapsible>
          ) : null}
          {TRIGGER_NOTES[kind].length > 0 ? (
            <ul className="space-y-1 text-meta text-muted-foreground" data-testid="flow-gateway-notes">
              {TRIGGER_NOTES[kind].map((n) => <li key={n}>{n}</li>)}
            </ul>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
