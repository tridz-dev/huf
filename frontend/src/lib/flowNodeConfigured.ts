import type { ActionConfig, FlowNodeData } from '../types/flow.types';

/**
 * Whether an action node carries user-entered configuration worth protecting
 * from an accidental delete-click.
 *
 * `data.configured` alone is not a reliable signal for actions: the node
 * picker stamps `configured: true` the moment an action TYPE is chosen, before
 * any field is filled in. So we check the fields a user would actually enter.
 */
export function actionHasConfiguredContent(data: Pick<FlowNodeData, 'actionConfig' | 'configured'>): boolean {
  const config: ActionConfig | undefined = data.actionConfig;
  if (!config || !config.type) return false;

  switch (config.type) {
    case 'agent-run':
      return Boolean(config.agent_name?.trim());
    case 'tool-call':
      return Boolean(config.tool_name?.trim());
    case 'router':
      return Boolean(config.router_agent_name?.trim());
    case 'human.approval':
      return Boolean(
        config.assigned_role?.trim() || (config.assigned_user && config.assigned_user.length > 0)
      );
    case 'condition':
      return Boolean(config.expression?.trim() || config.true_node?.trim() || config.false_node?.trim());
    case 'http-request':
      return Boolean(config.url?.trim());
    case 'transform':
      return Boolean(config.op?.trim());
    case 'state-get':
    case 'state-set':
    case 'state-delete':
      return Boolean(config.key !== undefined && config.key !== '' && config.key !== null);
    case 'doc-create':
      return Boolean(config.doctype?.trim());
    case 'unknown':
      return true;
    case 'loop':
      return Boolean(config.iterate_over?.trim());
    default:
      // Unhandled action shape: fall back to the coarse flag rather than
      // silently skipping the confirmation.
      return data.configured;
  }
}
