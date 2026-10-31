import type { FlowNodeData } from '../../types/flow.types';

/** Every card is the same size, whatever its state: nothing reflows when a step becomes valid or fails. */
export const NODE_CARD_BASE = 'relative flex h-[100px] w-[236px] flex-col justify-center p-3 transition-colors duration-200 bg-panel border-line';
export const NODE_HANDLE = 'w-3.5 h-3.5 !bg-ink border-2 border-panel';
export const NODE_ICON_WELL = 'w-7 h-7 rounded-lg bg-paper-deep flex items-center justify-center';

export function getExecutionStatusClasses(
  status: FlowNodeData['status'] | undefined,
  selected: boolean,
  options?: { unconfigured?: boolean }
): string {
  if (status === 'running') {
    return 'ring-2 ring-signal border-signal ring-offset-2 ring-offset-background motion-safe:animate-pulse';
  }
  if (status === 'success') {
    return 'border-good';
  }
  if (status === 'error') {
    return 'border-destructive ring-1 ring-destructive';
  }
  if (status === 'waiting') {
    return 'border-signal ring-1 ring-signal';
  }
  if (selected) {
    return 'border-[1.5px] border-signal shadow-sm';
  }
  if (options?.unconfigured) {
    return 'border-signal';
  }
  return 'border-line';
}

/** Spreads the `count` branch handles of a step evenly along its bottom edge. */
export const handleSpread = (index: number, count: number) => ({
  left: `${((index + 1) / (count + 1)) * 100}%`,
});
