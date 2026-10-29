import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Loader2, Plus } from 'lucide-react';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { DialogScrollBody, DialogScrollContent, DialogScrollHeader } from '@/components/ui/dialog-scroll';
import { paletteIcon, NODE_ICONS } from '@/components/nodes/nodeIcons';
import { triggerOptions } from '@/data/triggers';
import { FLOW_TEMPLATES, TEMPLATE_GROUPS, templateSteps, templateTrigger, type FlowTemplate } from '@/data/flowTemplates';
import { stepInfo } from '@/lib/flow-list/flowListSummary';
import { humanizeFlowError } from '@/lib/flow-graph/flowValidation';
import { toast } from '@/lib/toast';
import { createFlowFromTemplate } from '@/services/flow/flowCardsApi';
import { useFlowContext } from '@/contexts/FlowContext';
import { cn } from '@/lib/utils';

interface NewFlowDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const GROUP_TITLE: Record<FlowTemplate['group'], string> = {
  Starter: 'Simple starters',
  AI: 'With AI',
  People: 'With people',
  'Connected apps': 'With your apps',
};

function TemplateIcons({ template }: { template: FlowTemplate }) {
  const triggerIcon = triggerOptions.find((t) => t.id === templateTrigger(template))?.icon;
  const TriggerIcon = NODE_ICONS[triggerIcon ?? ''] ?? paletteIcon(undefined);
  const steps = templateSteps(template);
  const shown = steps.slice(0, 5);
  return (
    <div className="flex items-center gap-1" data-testid="flow-template-steps" aria-hidden>
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-signal/10 text-signal-ink" title="What starts it">
        <TriggerIcon className="h-3.5 w-3.5" />
      </span>
      {shown.map((step, i) => {
        const info = stepInfo(step);
        const Icon = paletteIcon(info.icon);
        return (
          <span key={i} title={info.name} className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-line bg-background text-steel">
            <Icon className="h-3.5 w-3.5" />
          </span>
        );
      })}
      {steps.length > shown.length && <span className="pl-0.5 text-xs text-steel">+{steps.length - shown.length}</span>}
    </div>
  );
}

/**
 * "New flow": start from scratch, or pick a template that is copied into a new draft you own. Templates are the
 * ready-made small flows from the catalog (data/flowTemplates.ts); nothing is shared with the original.
 */
export function NewFlowDialog({ open, onOpenChange }: NewFlowDialogProps) {
  const navigate = useNavigate();
  const { createFlow } = useFlowContext();
  const [busy, setBusy] = useState<string | null>(null);

  const startScratch = async () => {
    setBusy('scratch');
    try {
      const flow = await createFlow('New Flow', 'Uncategorized');
      onOpenChange(false);
      navigate(`/flows/${flow.id}`);
    } catch (err) {
      toast.error('Could not create the flow', { description: humanizeFlowError(err) });
    } finally {
      setBusy(null);
    }
  };

  const startTemplate = async (template: FlowTemplate) => {
    setBusy(template.id);
    try {
      const created = await createFlowFromTemplate({
        name: template.name,
        description: template.description,
        category: '',
        definition: template.graph,
      });
      onOpenChange(false);
      navigate(`/flows/${created.flow_id}`);
      if (created.needs_setup.length > 0) {
        toast.info(`"${created.flow_name}" is ready. Finish setting it up`, {
          description: created.needs_setup.map((n) => `${n.title}: ${n.what}`).join('. '),
        });
      } else {
        toast.success(`Created "${created.flow_name}"`, { description: 'It is a draft. Open a step to change it, then publish when you are ready.' });
      }
    } catch (err) {
      toast.error('Could not create the flow', { description: humanizeFlowError(err) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (busy ? undefined : onOpenChange(next))}>
      <DialogScrollContent className="sm:max-w-3xl" data-testid="flow-new-dialog">
        <DialogScrollHeader>
          <DialogTitle>New flow</DialogTitle>
          <DialogDescription>Start with a blank flow, or copy a ready-made one and change it. Nothing runs until you publish.</DialogDescription>
        </DialogScrollHeader>
        <DialogScrollBody className="space-y-6 py-4">
          <button
            type="button"
            onClick={startScratch}
            disabled={busy !== null}
            className="flex w-full items-center gap-3 rounded-lg border border-dashed border-line bg-panel p-4 text-left transition-colors hover:border-ink disabled:opacity-60"
            data-testid="flow-new-scratch"
          >
            <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-line bg-background">
              {busy === 'scratch' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" aria-hidden />}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-body-text font-semibold text-ink">Start from scratch</span>
              <span className="block text-ui-text text-steel">An empty flow. You choose what starts it and add the steps.</span>
            </span>
            <ArrowRight className="h-4 w-4 shrink-0 text-steel-soft" aria-hidden />
          </button>

          {TEMPLATE_GROUPS.map((group) => {
            const templates = FLOW_TEMPLATES.filter((t) => t.group === group);
            if (templates.length === 0) return null;
            return (
              <section key={group} aria-label={GROUP_TITLE[group]} data-testid={`flow-templates-${group.toLowerCase().replace(/\s+/g, '-')}`}>
                <h3 className="mb-2 text-sm font-medium text-steel">{GROUP_TITLE[group]}</h3>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {templates.map((template) => (
                    <button
                      key={template.id}
                      type="button"
                      onClick={() => startTemplate(template)}
                      disabled={busy !== null}
                      className={cn(
                        'flex min-w-0 flex-col gap-2 rounded-lg border border-line bg-panel p-3 text-left transition-colors hover:border-ink disabled:opacity-60',
                        busy === template.id && 'border-ink',
                      )}
                      data-testid={`flow-template-${template.id}`}
                    >
                      <span className="flex items-start justify-between gap-2">
                        <span className="min-w-0 line-clamp-2 text-body-text font-semibold leading-snug text-ink" title={template.name}>
                          {template.name}
                        </span>
                        {busy === template.id && <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin" aria-label="Creating" />}
                      </span>
                      <span className="line-clamp-2 text-ui-text text-steel">{template.description}</span>
                      <TemplateIcons template={template} />
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
        </DialogScrollBody>
      </DialogScrollContent>
    </Dialog>
  );
}
