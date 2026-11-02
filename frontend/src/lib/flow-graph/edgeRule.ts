import { branchHandlesFor } from '../flow/flowBranches';
import type { FlowEdgeRoute } from '../../types/flow.types';

type StepCfg = ({ type?: string } & Record<string, unknown>) | undefined;

export interface EdgeRule {
  /** Short heading naming the kind of connection ("Loop: for each item"). */
  heading: string;
  /** One plain sentence saying when the second step runs. */
  sentence: string;
  /** Part of a loop (its items or its end), which the panel marks apart. */
  loop: boolean;
}

/** Plain-language meaning of a connection, for the connection panel. `from` / `to` are step titles. */
export function edgeRule(route: FlowEdgeRoute, from: string, to: string, fromCfg: StepCfg, pathName?: string): EdgeRule {
  const isLoop = fromCfg?.type === 'foreach';
  const branch = branchHandlesFor(fromCfg?.type, fromCfg).find((h) => h.route === route)?.label;
  switch (route) {
    case 'true':
      return { heading: `If ${branch ?? 'Yes'}`, sentence: `When the answer to "${from}" is Yes, "${to}" runs.`, loop: false };
    case 'false':
      return { heading: `If ${branch ?? 'No'}`, sentence: `When the answer to "${from}" is No, "${to}" runs.`, loop: false };
    case 'approve':
      return { heading: 'If approved', sentence: `When someone approves "${from}", "${to}" runs.`, loop: false };
    case 'reject':
      return { heading: 'If rejected', sentence: `When someone rejects "${from}", "${to}" runs.`, loop: false };
    case 'timeout':
      return { heading: 'If nobody answers', sentence: `When nobody answers "${from}" in time, "${to}" runs.`, loop: false };
    case 'body':
      return { heading: 'Loop: for each item', sentence: `"${to}" runs once for each item in "${from}".`, loop: true };
    case 'option':
      return { heading: 'A path the AI can choose', sentence: `When the AI picks the path "${pathName || to}", "${to}" runs.`, loop: false };
    case 'default':
      return { heading: 'Otherwise', sentence: `When no other path fits, "${to}" runs.`, loop: false };
    case 'error':
      return { heading: 'If the step fails', sentence: `When "${from}" fails, "${to}" runs.`, loop: false };
    default:
      return isLoop
        ? { heading: 'Loop: when done', sentence: `After "${from}" has gone through every item, "${to}" runs.`, loop: true }
        : { heading: 'Runs next', sentence: `When "${from}" finishes, "${to}" runs.`, loop: false };
  }
}
