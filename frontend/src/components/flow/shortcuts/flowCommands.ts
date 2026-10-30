/**
 * Editor commands that more than one place can start (a shortcut, the Cmd+K palette, a menu): the header owns what they do
 * (save, run, publish, the dialogs), so they are sent to it by name. One listener per command; the header registers them.
 */
import { useEffect, useRef } from 'react';

export type FlowCommand = 'save' | 'run' | 'publish' | 'settings' | 'runs' | 'palette';

type Handler = () => void;
const handlers = new Map<FlowCommand, Set<Handler>>();

/** Ask the editor to do `command`. Returns false when nothing is listening (so a caller can say so). */
export function runFlowCommand(command: FlowCommand): boolean {
  const set = handlers.get(command);
  if (!set || set.size === 0) return false;
  set.forEach((h) => h());
  return true;
}

export function onFlowCommand(command: FlowCommand, handler: Handler): () => void {
  const set = handlers.get(command) ?? new Set<Handler>();
  set.add(handler);
  handlers.set(command, set);
  return () => {
    set.delete(handler);
  };
}

/** Register the latest `handler` for `command` for as long as the component is mounted. */
export function useFlowCommand(command: FlowCommand, handler: Handler, enabled = true): void {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    if (!enabled) return;
    return onFlowCommand(command, () => ref.current());
  }, [command, enabled]);
}
