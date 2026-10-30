import { memo, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { BaseEdge, EdgeLabelRenderer, EdgeProps, useStore } from 'reactflow';
import { Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { routeEdge, routeLoopBack, type Rect } from '@/lib/flow-graph/edgeRouting';
import { PLACED_PILLS, boxAt, controlCandidates, pillCandidates, placeClear, type Size } from '@/lib/flow-graph/edgePlacement';
import type { BranchTone } from '@/lib/flow/flowBranches';
import type { FlowEdgeRoute } from '../../types/flow.types';
import { counterScale, lodForZoom } from '@/lib/flow-canvas/zoomLod';
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
  /** A run opened on the canvas: the line it went along (green) or did not (faded). */
  run?: 'taken' | 'untaken';
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
/** The "+" and remove buttons: 28px round, 6px apart (h-7 w-7, gap-1.5). */
const BUTTON_PX = 28;
const BUTTON_GAP_PX = 6;
/** Width of a step shown as an icon tile (under 50% zoom), centred in the step's box (see NodeCard). */
const TILE_WIDTH = 120;


/**
 * Places an overlay centred at a point on the canvas at `scale` times its normal size (a 12px label is made 12px on screen when
 * the canvas is zoomed out instead of shrinking with the steps).
 */
const overlayStyle = (x: number, y: number, scale: number, interactive = false): CSSProperties => ({
  position: 'absolute',
  // Scale around the top-left corner: the centre of the overlay then lands exactly on (x, y) at every zoom (around the middle it drifted away from it when scaled).
  transformOrigin: '0 0',
  transform: `translate(${x}px, ${y}px) scale(${scale}) translate(-50%, -50%)`,
  ...(interactive ? { pointerEvents: 'all' as const } : {}),
});

/**
 * Where a branch name sits: right where the line turns down into its step (each branch ends over its own column, so names
 * never pile up, however far the canvas is zoomed out), or just under the step it leaves when the line runs straight down.
 */
function pillPoint(routed: ReturnType<typeof routeEdge>, scale: number, option: boolean) {
  const [first, ...rest] = routed.points;
  const turn = rest.find((p, i) => i > 0 && Math.abs(p.y - rest[i - 1].y) < 0.5 && Math.abs(p.x - rest[i - 1].x) >= 40);
  const run = turn ? rest[rest.indexOf(turn) - 1] : undefined;
  if (turn && run && first) return { x: turn.x, y: turn.y };
  if (!option) return routed.pillAt;
  return routed.pointAt(Math.max(Math.min(Math.max(routed.length * 0.4, 28 + 14 * scale), routed.length / 2), 10));
}

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
    // The buttons only take the pointer while shown (invisible ones must not catch clicks meant for the steps); a short grace
    // period lets the pointer travel from the line onto them.
    const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const hoverOn = () => { if (leaveTimer.current) clearTimeout(leaveTimer.current); setHovered(true); };
    const hoverOff = () => { if (leaveTimer.current) clearTimeout(leaveTimer.current); leaveTimer.current = setTimeout(() => setHovered(false), 160); };
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

    const run = data?.run;
    const lineStyle = selected
      ? { ...style, stroke: 'var(--signal)', strokeWidth: 2.5 }
      : run === 'taken'
        ? { ...style, stroke: 'var(--good)', strokeWidth: 3, ...(loopBack ? { strokeDasharray: '6 4' } : {}) }
        : { ...style, stroke: 'var(--steel-soft)', strokeWidth: 1.75, ...(run === 'untaken' ? { opacity: 0.4 } : {}), ...(loopBack ? { strokeDasharray: '6 4' } : {}) };
    const pill = data?.pill;
    // Router paths all leave one dot: their names go partway along each line so they never pile up.
    const scale = Math.max(counterScale(zoom), 1);
    const pillBase = loopBack ? routed.pillAt : pillPoint(routed, scale, data?.route === 'option');
    // A name sitting right under its step is pushed down as it is scaled up, so it never covers the step's edge.
    const pillWanted = data?.route !== 'option' && pillBase.x === routed.points[0]?.x && pillBase.y < (routed.points[0]?.y ?? 0) + 24 ? { x: pillBase.x, y: pillBase.y + (scale - 1) * 8 } : pillBase;
    // The name's size on the canvas (its own size on screen, scaled like the name itself), so it can be kept off the steps.
    const pillRef = useRef<HTMLDivElement>(null);
    const [pillCss, setPillCss] = useState<Size | null>(null);
    useLayoutEffect(() => {
      const el = pillRef.current;
      if (el && el.offsetWidth > 0 && (!pillCss || Math.abs(pillCss.width - el.offsetWidth) > 0.5 || Math.abs(pillCss.height - el.offsetHeight) > 0.5)) setPillCss({ width: el.offsetWidth, height: el.offsetHeight });
    }, [pill, pillCss]);
    const pillScale = counterScale(zoom);
    const pillSize = useMemo<Size>(() => ({ width: (pillCss?.width ?? Math.min(220, 8 * (pill?.length ?? 0) + 22)) * pillScale, height: (pillCss?.height ?? 20) * pillScale }), [pillCss, pill, pillScale]);
    // What of each step is drawn: an icon tile is narrower than the box the step takes, so names and buttons may sit beside it.
    const lod = lodForZoom(zoom);
    const stepBoxes = useMemo(() => [...obstacles.values()].map((r) => (lod === 'icon' ? { ...r, x: r.x + (r.width - TILE_WIDTH) / 2, width: TILE_WIDTH } : r)), [obstacles, lod]);
    const pillPos = useMemo(
      () => (pill && !loopBack ? placeClear(pillSize, stepBoxes, pillWanted, pillCandidates(pillWanted)) : pillWanted),
      [pill, loopBack, pillSize, stepBoxes, pillWanted.x, pillWanted.y], // eslint-disable-line react-hooks/exhaustive-deps
    );
    useLayoutEffect(() => {
      if (!pill || loopBack) return undefined;
      PLACED_PILLS.set(id, boxAt(pillPos, pillSize));
      return () => { PLACED_PILLS.delete(id); };
    }, [id, pill, loopBack, pillPos, pillSize]);
    const showControls = canManage && (hovered || selected);
    // The buttons keep off the name, the steps and the arrow head: further along the line, or beside it when the line is full.
    const buttons = selected && !loopBack ? 2 : 1;
    // About 22px across on screen when zoomed out (up to 2.5 times their size), so they fit the gap between two steps more often.
    const buttonScale = zoom < 1 ? Math.max(Math.min(counterScale(zoom, 2.5), 22 / (BUTTON_PX * zoom)), 1) : 1;
    const controlsSize = useMemo<Size>(() => ({ width: (buttons * BUTTON_PX + (buttons - 1) * BUTTON_GAP_PX) * buttonScale, height: BUTTON_PX * buttonScale }), [buttons, buttonScale]);
    const controlsPos = useMemo(() => {
      if (!showControls) return routed.controlsAt;
      const end = routed.points[routed.points.length - 1];
      const avoid = [...stepBoxes];
      if (end) avoid.push(loopBack ? { x: end.x - 2, y: end.y - 10, width: 24, height: 20 } : { x: end.x - 10, y: end.y - 18, width: 20, height: 22 });
      PLACED_PILLS.forEach((box) => avoid.push(box));
      return placeClear(controlsSize, avoid, routed.controlsAt, controlCandidates(routed.points, routed.length, controlsSize, routed.controlsAt));
    }, [showControls, routed, stepBoxes, loopBack, pill, pillPos, pillSize, controlsSize]);

    return (
      <>
        <BaseEdge id={id} path={routed.path} style={lineStyle} markerEnd={markerEnd} interactionWidth={24} />
        {run === 'taken' && <title>{'This run went this way'}</title>}
        {/* Wider, invisible hit area so the hover affordance is easy to reach. */}
        <path
          d={routed.path}
          fill="none"
          stroke="transparent"
          strokeWidth={24}
          className="cursor-pointer"
          onMouseEnter={hoverOn}
          onMouseLeave={hoverOff}
          data-testid={`flow-edge-line-${id}`}
        />
        <EdgeLabelRenderer>
          {pill ? (
            <div
              ref={pillRef}
              data-testid={`flow-edge-label-${id}`}
              data-source={source}
              title={pill}
              onClick={() => data?.onSelect?.(id)}
              onMouseEnter={hoverOn}
              onMouseLeave={hoverOff}
              style={overlayStyle(pillPos.x, pillPos.y, pillScale, !data?.loopBack)}
              className={cn(
                'max-w-[220px] cursor-pointer whitespace-normal break-words rounded-full border px-2.5 py-px text-center text-xs font-medium leading-tight shadow-sm',
                PILL_TONE[data?.tone ?? 'neutral'],
                run === 'untaken' && 'opacity-50',
              )}
              data-run={run}
            >
              {pill}
            </div>
          ) : null}
          {canManage && (
            <div
              style={overlayStyle(controlsPos.x, controlsPos.y, buttonScale, showControls)}
              onMouseEnter={hoverOn}
              onMouseLeave={hoverOff}
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
