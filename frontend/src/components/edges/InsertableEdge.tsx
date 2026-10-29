import { memo, useMemo, useState, type CSSProperties } from 'react';
import { BaseEdge, EdgeLabelRenderer, EdgeProps, useStore } from 'reactflow';
import { Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { routeEdge, routeLoopBack, type Rect } from '@/lib/flow-graph/edgeRouting';
import type { BranchTone } from '@/lib/flow/flowBranches';
import type { FlowEdgeRoute } from '../../types/flow.types';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/tooltip';

export interface InsertableEdgeData {
  /** The node id a newly inserted action should be attached after (the edge's source). */
  sourceNodeId: string;
  route?: FlowEdgeRoute;
  /** Plain name of the branch ("Yes", "Approved", a router path), drawn as a pill near the step it leaves. */
  pill?: string | null;
  tone?: BranchTone;
  /** Render-only line from the last step of a loop's body back to the loop. */
  loopBack?: boolean;
  onInsertNode?: (sourceNodeId: string, route?: FlowEdgeRoute) => void;
  /** Ask to remove this connection (the canvas confirms first). */
  onRemove?: (edgeId: string) => void;
  /** Select this connection (the name pill is a click target too). */
  onSelect?: (edgeId: string) => void;
}

/** Colour family per branch kind: green yes/approved, red no/rejected/failed, amber timed out, grey otherwise. */
const PILL_TONE: Record<BranchTone, string> = {
  good: 'border-good/40 bg-good-tint text-good',
  bad: 'border-destructive/40 bg-destructive-tint text-destructive',
  warn: 'border-signal/50 bg-panel text-signal-ink',
  loop: 'border-line-dark bg-paper-deep text-ink-soft',
  neutral: 'border-line-dark bg-panel text-ink-soft',
};

const GHOST_LINE: CSSProperties = { stroke: 'var(--steel-soft)', strokeWidth: 1.5, strokeDasharray: '4 4', opacity: 0.7 };
const DEFAULT_SIZE = { width: 236, height: 70 };

/**
 * Places an overlay centred at a point on the canvas and keeps it at its normal size when the canvas is zoomed out
 * (a 12px label stays 12px on screen instead of shrinking with the steps).
 */
const overlayStyle = (x: number, y: number, zoom: number, interactive = false): CSSProperties => ({
  position: 'absolute',
  transform: `translate(${x}px, ${y}px) scale(${zoom < 1 ? Math.min(1 / zoom, 3) : 1}) translate(-50%, -50%)`,
  ...(interactive ? { pointerEvents: 'all' as const } : {}),
});

/** Every step on the canvas as a box, so lines can stay clear of them. */
function useObstacles(): Map<string, Rect> {
  const internals = useStore((s) => s.nodeInternals);
  return useMemo(() => {
    const out = new Map<string, Rect>();
    internals.forEach((n, id) => {
      const p = n.positionAbsolute ?? n.position;
      out.set(id, { x: p.x, y: p.y, width: n.width ?? DEFAULT_SIZE.width, height: n.height ?? DEFAULT_SIZE.height });
    });
    return out;
  }, [internals]);
}

function ControlButton({ label, testId, onClick, className, children }: { label: string; testId: string; onClick: () => void; className?: string; children: React.ReactNode }) {
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={label}
            data-testid={testId}
            onClick={(e) => {
              e.stopPropagation();
              onClick();
            }}
            className={cn('flex h-7 w-7 items-center justify-center rounded-full border border-line-dark bg-panel shadow-sm transition-colors', className)}
          >
            {children}
          </button>
        </TooltipTrigger>
        <TooltipContent side="top">{label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/**
 * Edge between two real, already-connected nodes. Orthogonal line that stays clear of every other step, a pill with
 * the plain branch name next to the step it leaves, and (on hover or when selected) a "+" that inserts a step on the
 * line and a button that removes the connection.
 */
export const InsertableEdge = memo(
  ({ id, source, target, sourceX, sourceY, targetX, targetY, style, markerEnd, data, selected }: EdgeProps<InsertableEdgeData>) => {
    const [hovered, setHovered] = useState(false);
    const { canManage } = useFlowPermissions();
    const zoom = useStore((s) => s.transform[2]);
    const obstacles = useObstacles();
    const loopBack = data?.loopBack === true;

    const routed = useMemo(() => {
      const all = [...obstacles.values()];
      const loop = obstacles.get(target);
      if (loopBack && loop) return routeLoopBack({ x: sourceX, y: sourceY }, loop, all);
      return routeEdge({ x: sourceX, y: sourceY }, { x: targetX, y: targetY }, all);
    }, [obstacles, loopBack, target, sourceX, sourceY, targetX, targetY]);

    const lineStyle = selected
      ? { ...style, stroke: 'var(--signal)', strokeWidth: 2.5 }
      : { ...style, stroke: 'var(--steel-soft)', strokeWidth: 1.75, ...(loopBack ? { strokeDasharray: '6 4' } : {}) };
    const pill = data?.pill;
    // Router paths all leave one dot: their names go partway along each line so they never pile up.
    const scale = zoom < 1 ? Math.min(1 / zoom, 3) : 1;
    const pillBase = data?.route === 'option' ? routed.pointAt(Math.min(Math.max(routed.length * 0.4, 28 + 14 * scale), Math.max(routed.length - 40, 0))) : routed.pillAt;
    // A name sitting right under its step is pushed down as it is scaled up, so it never covers the step's edge.
    const pillPos = data?.route !== 'option' && pillBase.x === routed.points[0]?.x && pillBase.y < (routed.points[0]?.y ?? 0) + 24 ? { x: pillBase.x, y: pillBase.y + (scale - 1) * 8 } : pillBase;
    const showControls = canManage && (hovered || selected);

    return (
      <>
        <BaseEdge id={id} path={routed.path} style={lineStyle} markerEnd={markerEnd} interactionWidth={24} />
        {/* Wider, invisible hit area so the hover affordance is easy to reach. */}
        <path
          d={routed.path}
          fill="none"
          stroke="transparent"
          strokeWidth={24}
          className="cursor-pointer"
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          data-testid={`flow-edge-line-${id}`}
        />
        <EdgeLabelRenderer>
          {pill ? (
            <div
              data-testid={`flow-edge-label-${id}`}
              data-source={source}
              title={pill}
              onClick={() => data?.onSelect?.(id)}
              style={overlayStyle(pillPos.x, pillPos.y, zoom, !data?.loopBack)}
              className={cn(
                'max-w-[220px] cursor-pointer whitespace-normal break-words rounded-full border px-2.5 py-0.5 text-center text-xs font-medium leading-tight shadow-sm',
                PILL_TONE[data?.tone ?? 'neutral'],
              )}
            >
              {pill}
            </div>
          ) : null}
          {canManage && (
            <div
              style={overlayStyle(routed.controlsAt.x, routed.controlsAt.y, zoom, true)}
              onMouseEnter={() => setHovered(true)}
              onMouseLeave={() => setHovered(false)}
              className={cn('nodrag nopan z-10 flex items-center gap-1.5 transition-opacity duration-150', showControls ? 'opacity-100' : 'opacity-0 hover:opacity-100 focus-within:opacity-100')}
              data-testid={`flow-edge-controls-${id}`}
            >
              <ControlButton
                label="Add a step here"
                testId={`flow-insert-step-${id}`}
                onClick={() => data?.onInsertNode?.(data.sourceNodeId, data.route)}
                className="text-muted-foreground hover:border-steel-soft hover:text-ink"
              >
                <Plus className="h-4 w-4" />
              </ControlButton>
              {selected && !loopBack && (
                <ControlButton
                  label="Remove connection"
                  testId={`flow-edge-remove-${id}`}
                  onClick={() => data?.onRemove?.(id)}
                  className="text-destructive hover:bg-destructive/10"
                >
                  <Trash2 className="h-4 w-4" />
                </ControlButton>
              )}
            </div>
          )}
        </EdgeLabelRenderer>
      </>
    );
  }
);

InsertableEdge.displayName = 'InsertableEdge';

/** Plain, render-only line to an "Add step" card: dashed and quiet, routed like the real ones. */
export const GhostEdge = memo(({ id, sourceX, sourceY, targetX, targetY }: EdgeProps) => {
  const obstacles = useObstacles();
  const routed = useMemo(() => routeEdge({ x: sourceX, y: sourceY }, { x: targetX, y: targetY }, [...obstacles.values()]), [obstacles, sourceX, sourceY, targetX, targetY]);
  return <BaseEdge id={id} path={routed.path} style={GHOST_LINE} />;
});

GhostEdge.displayName = 'GhostEdge';
