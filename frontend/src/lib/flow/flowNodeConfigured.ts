import type { ActionConfig, FlowNodeData } from '../../types/flow.types';

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

  const has = (v: unknown) => typeof v === 'string' && v.trim() !== '';
  switch (config.type) {
    case 'agent-run':
      return has(config.agent) || has(config.prompt);
    case 'tool-call':
      return has(config.tool_id);
    case 'router':
      return has(config.prompt);
    case 'human.approval':
      return has(config.message) || has(config.approver_role) || Boolean(config.approver_users && config.approver_users.length > 0);
    case 'condition':
      return has(config.expression);
    case 'foreach':
      return has(config.items?.$from) || has(config.collect?.$from);
    case 'transform':
      return Boolean(config.op?.trim());
    case 'state-get':
    case 'state-set':
    case 'state-delete':
      return Boolean(config.key !== undefined && config.key !== '' && config.key !== null);
    case 'doc-create':
      return Boolean(config.doctype?.trim());
    case 'code-run':
      return has(config.code);
    case 'unknown':
      return true;
    default:
      // Unhandled action shape: fall back to the coarse flag rather than
      // silently skipping the confirmation.
      return data.configured;
  }
}
