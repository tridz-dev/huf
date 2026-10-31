import { useEffect, useRef } from 'react';
import { isEditableTarget } from '@/lib/shortcuts/matching';
import { FLOW_PANEL_ATTR } from '../canvas/KeepSelectedVisible';
import { runFlowCommand } from './flowCommands';

export interface FlowShortcutHandlers {
  palette: () => void;
  undo: () => void;
  redo: () => void;
  duplicate: () => void;
  copy: () => void;
  paste: () => void;
  selectAll: () => void;
  /** Nothing to save / run is said by the owner of the command. */
}

interface Options {
  /** Off on a phone (nothing is edited there). */
  enabled: boolean;
  /** Edit rights: without them only the palette answers. */
  canManage: boolean;
  handlers: FlowShortcutHandlers;
}

/** An open dialog (not the step panel, which is a sheet on narrow screens but is part of the editor). */
export function blockingDialogOpen(): boolean {
  const open = document.querySelectorAll('[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]');
  return Array.from(open).some((el) => !el.hasAttribute(FLOW_PANEL_ATTR) && !el.closest(`[${FLOW_PANEL_ATTR}]`));
}

const hasTextSelection = () => (window.getSelection()?.toString() ?? '') !== '';

/**
 * The editor's keyboard shortcuts: undo/redo, duplicate, copy/paste, select all, save, run and the Cmd+K palette. Cmd and Ctrl
 * both work on every system. Text fields keep their own Cmd+Z / Cmd+C / Cmd+V; save, run and the palette work from inside
 * them too. Nothing fires while a dialog is open (except Cmd+K, which closes the palette). Listens in the capture phase so
 * Cmd+K reaches the flow palette before the app-wide page palette.
 */
export function useFlowShortcuts({ enabled, canManage, handlers }: Options): void {
  const ref = useRef({ canManage, handlers });
  ref.current = { canManage, handlers };

  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.isComposing) return;
      const mod = e.metaKey || e.ctrlKey;
      if (!mod || e.altKey) return;
      const key = e.key.toLowerCase();
      const { canManage: manage, handlers: h } = ref.current;
      const editable = isEditableTarget(e.target as HTMLElement | null);
      const paletteOpen = Boolean(document.querySelector('[data-testid="flow-palette"][data-state="open"]'));

      if (key === 'k' && !e.shiftKey) {
        // The palette is itself a dialog: only it may be open.
        if (blockingDialogOpen() && !paletteOpen) return;
        e.preventDefault();
        e.stopPropagation();
        h.palette();
        return;
      }
      if (blockingDialogOpen() || paletteOpen) return;
      if (!manage) return;

      if (key === 's' && !e.shiftKey) {
        e.preventDefault();
        runFlowCommand('save');
        return;
      }
      if (key === 'enter' && !e.shiftKey) {
        e.preventDefault();
        runFlowCommand('run');
        return;
      }
      // Everything below belongs to the canvas, not to a text field.
      if (editable) return;
      if (key === 'z') {
        e.preventDefault();
        if (e.shiftKey) h.redo();
        else h.undo();
      } else if (key === 'y' && !e.shiftKey) {
        e.preventDefault();
        h.redo();
      } else if (key === 'd' && !e.shiftKey) {
        e.preventDefault(); // the browser would bookmark the page
        h.duplicate();
      } else if (key === 'c' && !e.shiftKey && !hasTextSelection()) {
        e.preventDefault();
        h.copy();
      } else if (key === 'v' && !e.shiftKey) {
        e.preventDefault();
        h.paste();
      } else if (key === 'a' && !e.shiftKey && !hasTextSelection()) {
        e.preventDefault();
        h.selectAll();
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [enabled]);
}
