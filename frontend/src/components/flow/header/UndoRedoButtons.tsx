import { Redo2, Undo2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useFlowContext } from '@/contexts/FlowContext';
import { HIT_TARGET } from '@/lib/ui/responsive';
import { cn } from '@/lib/utils';
import { withShortcut } from '../shortcuts/shortcutHints';

/**
 * Undo and Redo in the editor header. Each says what it would do in its tooltip ("Undo: moved a step").
 * At 1200px and narrower the same two (and Search) live in the "..." menu instead (see HeaderOverflowMenu).
 */
export function UndoRedoButtons() {
  const { undo, redo, canUndo, canRedo, undoLabel, redoLabel } = useFlowContext();
  const lower = (s?: string) => (s ? s.replace(/^./, (c) => c.toLowerCase()) : '');
  const hit = cn('px-0', HIT_TARGET);
  return (
    <div className="flex items-center gap-1" role="group" aria-label="History" data-testid="flow-history-buttons">
      <Button
        variant="ghost"
        size="icon"
        className={hit}
        data-testid="flow-undo"
        aria-label={canUndo ? `Undo: ${lower(undoLabel)}` : 'Undo'}
        title={canUndo ? withShortcut(`Undo: ${lower(undoLabel)}`, 'flow-undo') : 'Nothing to undo yet'}
        disabled={!canUndo}
        onClick={undo}
      >
        <Undo2 className="h-4 w-4" aria-hidden />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className={hit}
        data-testid="flow-redo"
        aria-label={canRedo ? `Redo: ${lower(redoLabel)}` : 'Redo'}
        title={canRedo ? withShortcut(`Redo: ${lower(redoLabel)}`, 'flow-redo') : 'Nothing to redo'}
        disabled={!canRedo}
        onClick={redo}
      >
        <Redo2 className="h-4 w-4" aria-hidden />
      </Button>
    </div>
  );
}
