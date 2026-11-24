import { actionCardId, actionLabel } from '@/lib/flow/flowLabels';
import { str, tid, useNodeForm } from './forms/formKit';
import { TriggerConfigForm } from './forms/TriggerConfigForm';
import { AgentRunForm } from './forms/AgentRunForm';
import { ToolCallForm } from './forms/tool/ToolCallForm';
import { RouterForm } from './forms/RouterForm';
import { SwitchForm } from './forms/SwitchForm';
import { ConditionForm } from './forms/ConditionForm';
import { LoopForm } from './forms/LoopForm';
import { ApprovalForm } from './forms/approval/ApprovalForm';
import { WaitForm } from './forms/WaitForm';
import { StopForm } from './forms/StopForm';
import { FlowCallForm } from './forms/FlowCallForm';
import { DocGetForm } from './forms/data/DocGetForm';
import { DocUpdateForm } from './forms/data/DocUpdateForm';
import { TransformForm } from './forms/data/TransformForm';
import { StateForm } from './forms/data/StateForm';
import { DocCreateForm } from './forms/data/DocCreateForm';
import { Section } from './forms/formKit';
import { SchemaNodeForm } from './forms/SchemaNodeForm';
import { getAppNodeType, useAppNodeTypes } from '@/lib/flow-graph/appNodeTypes';
import { CodeRunFields } from './CodeRunForm';

export { TriggerConfigForm };

/** The settings form of one action step: picks the form for the step's type. */
export function ActionConfigForm({ nodeId }: { nodeId: string }) {
  const { node, cfg, patch, kind, shell } = useNodeForm(nodeId, 'actionConfig');
  const { loaded } = useAppNodeTypes();
  if (!node) return null;
  const type = str(cfg.type);
  const common = {
    nodeId,
    cfg,
    patch,
    f: (field: string) => tid(kind, field),
    Err: shell.Err,
    title: actionLabel(actionCardId(cfg as { type?: unknown; tool_id?: unknown })),
  };

  switch (type) {
    case 'agent-run':
      return <AgentRunForm {...common} />;
    case 'tool-call':
      return <ToolCallForm {...common} />;
    case 'router':
      return <RouterForm {...common} />;
    case 'router-decision':
      return <SwitchForm {...common} />;
    case 'condition':
      return <ConditionForm {...common} />;
    case 'foreach':
      return <LoopForm {...common} />;
    case 'human.approval':
      return <ApprovalForm {...common} />;
    case 'wait':
      return <WaitForm {...common} />;
    case 'stop':
      return <StopForm {...common} />;
    case 'flow-call':
      return <FlowCallForm {...common} />;
    case 'doc-get':
      return <DocGetForm {...common} />;
    case 'doc-update':
      return <DocUpdateForm {...common} />;
    case 'transform':
      return <TransformForm {...common} />;
    case 'state-get':
    case 'state-set':
    case 'state-delete':
      return <StateForm {...common} />;
    case 'doc-create':
      return <DocCreateForm {...common} />;
    case 'code-run':
      return (
        <Section title={common.title} hint="Runs Python you write in a sandbox. The flow continues with what your code prints and returns.">
          <CodeRunFields nodeId={nodeId} cfg={cfg} patch={patch} Err={shell.Err} />
        </Section>
      );
    case 'unknown':
      // Until the app step types load, keep the plain note; then an app's step gets its schema form (or the not-installed card).
      if (loaded) return <SchemaNodeForm {...common} />;
      return (
        <div className="text-xs text-muted-foreground p-2 bg-muted/30 rounded-md">
          This step type cannot be edited here. It is kept as it is and saved unchanged.
        </div>
      );
    default:
      return null;
  }
}
