import { Link } from 'react-router-dom';
import { Maximize2, Plus, Sparkles, LayoutTemplate } from 'lucide-react';
import { Button } from '../../ui/button';

interface FlowCanvasToolbarProps {
  canManage: boolean;
  readOnlyReason: string | null | undefined;
  hasTrigger: boolean;
  /** More than the trigger alone is on the canvas. */
  hasSteps: boolean;
  convertedProcedure: string | null;
  onAddTrigger: () => void;
  onTidy: () => void;
  onConvert: () => void;
  onTogglePanels: () => void;
}

/** Buttons in the canvas's top-right corner: add trigger, tidy layout, procedure conversion, panel toggle. */
export function FlowCanvasToolbar({
  canManage, readOnlyReason, hasTrigger, hasSteps, convertedProcedure, onAddTrigger, onTidy, onConvert, onTogglePanels,
}: FlowCanvasToolbarProps) {
  return (
    <div className="flex gap-2">
      {canManage && !hasTrigger && (
        <Button
          variant="default"
          size="sm"
          data-testid="flow-add-trigger"
          title="Choose what starts this flow"
          onClick={onAddTrigger}
        >
          <Plus className="w-4 h-4 mr-2" />
          Add trigger
        </Button>
      )}
      {hasSteps && (
        <Button
          variant="outline"
          size="sm"
          data-testid="flow-tidy-layout"
          disabled={!canManage}
          title={canManage ? 'Line the steps up neatly' : readOnlyReason ?? undefined}
          onClick={onTidy}
        >
          <LayoutTemplate className="w-4 h-4 mr-2" />
          Tidy layout
        </Button>
      )}
      {convertedProcedure && (
        <Link to={`/procedures/${convertedProcedure}`}>
          <Button variant="outline" size="sm">
            <Sparkles className="w-4 h-4 mr-2" />
            Saved as procedure
          </Button>
        </Link>
      )}
      {canManage && !convertedProcedure && (
        <Button
          variant="outline"
          size="sm"
          title="Save this flow as a reusable draft procedure (only for flows without AI-driven steps)"
          onClick={onConvert}
        >
          <Sparkles className="w-4 h-4 mr-2" />
          Convert to procedure
        </Button>
      )}
      <Button
        variant="outline"
        size="icon"
        className="h-control-lg w-control-lg"
        aria-label="Hide or show the side panels"
        title="Hide or show the side panels"
        data-testid="flow-toggle-panels"
        onClick={onTogglePanels}
      >
        <Maximize2 className="w-4 h-4" />
      </Button>
    </div>
  );
}
