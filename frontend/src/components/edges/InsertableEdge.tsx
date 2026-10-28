import { memo, useState } from 'react';
import { BaseEdge, EdgeLabelRenderer, EdgeProps, getBezierPath } from 'reactflow';
import { Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { FlowEdgeRoute } from '../../types/flow.types';

export interface InsertableEdgeData {
  /** The node id a newly inserted action should be attached after (the edge's source). */
  sourceNodeId: string;
  route?: FlowEdgeRoute;
  onInsertNode?: (sourceNodeId: string, route?: FlowEdgeRoute) => void;
  /** Ask to remove this connection (the canvas confirms first). */
  onRemove?: (edgeId: string) => void;
}

/**
 * Routes whose meaning is only on the edge (a router path's name, the error path). Every other branch
 * (True/False, Approved/Rejected/Timed out, For each item) is already named on the step's own handle, so
 * drawing it again on the edge made two labels collide near the step.
 */
const SHOWS_EDGE_LABEL = new Set<FlowEdgeRoute>(['option', 'error']);

/**
 * Edge between two real, already-connected nodes. Renders like a normal
 * edge at rest; on hover (or focus) it reveals a small "+" button at the
 * midpoint that inserts a new action node between the two endpoints,
 * reusing the same insertion logic as the trailing "Add step" ghost card
 * (`onAddNode`/`handleSelectAction` re-parents the downstream edge).
 */
export const InsertableEdge = memo(
  ({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, markerEnd, data, label, selected }: EdgeProps<InsertableEdgeData>) => {
    const [hovered, setHovered] = useState(false);
    const [edgePath, labelX, labelY] = getBezierPath({
      sourceX,
      sourceY,
      sourcePosition,
      targetX,
      targetY,
      targetPosition
    });

    return (
      <>
        <BaseEdge
          id={id}
          path={edgePath}
          style={selected ? { ...style, stroke: 'var(--signal)', strokeWidth: 3 } : style}
          markerEnd={markerEnd}
          interactionWidth={24}
        />
        {/* Wider, invisible hit area so the hover affordance is easy to reach. */}
        <path
          d={edgePath}
          fill="none"
          stroke="transparent"
          strokeWidth={20}
          className="cursor-pointer"
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          data-testid={`flow-edge-line-${id}`}
        />
        <EdgeLabelRenderer>
          {typeof label === 'string' && label && SHOWS_EDGE_LABEL.has(data?.route ?? 'next') ? (
            <div
              data-testid={`flow-edge-label-${id}`}
              title={label}
              style={{ position: 'absolute', transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY - 16}px)` }}
              className="max-w-[150px] truncate rounded bg-panel px-1.5 py-0.5 text-[10px] text-muted-foreground border border-line"
            >
              {label}
            </div>
          ) : null}
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'all'
            }}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
          >
            <button
              type="button"
              aria-label="Insert step"
              data-testid={`flow-insert-step-${id}`}
              onClick={(e) => {
                e.stopPropagation();
                data?.onInsertNode?.(data.sourceNodeId, data.route);
              }}
              className={cn(
                'flex items-center justify-center w-6 h-6 rounded-full border border-line bg-panel text-muted-foreground shadow-sm transition-all duration-150',
                'hover:border-steel-soft hover:text-ink hover:scale-110',
                (hovered || selected) ? 'opacity-100 scale-100' : 'opacity-0 scale-75'
              )}
            >
              <Plus className="w-3 h-3" />
            </button>
          </div>
          {selected && (
            <div
              style={{
                position: 'absolute',
                transform: `translate(-50%, -50%) translate(${labelX + 100}px, ${labelY}px)`,
                pointerEvents: 'all'
              }}
              className="nodrag nopan"
            >
              <button
                type="button"
                aria-label="Remove connection"
                title="Remove connection"
                data-testid={`flow-edge-remove-${id}`}
                onClick={(e) => {
                  e.stopPropagation();
                  data?.onRemove?.(id);
                }}
                className="flex items-center gap-1 rounded-md border border-line bg-panel px-2 py-1 text-xs text-destructive shadow-sm hover:bg-destructive/10"
              >
                <Trash2 className="w-3 h-3" />
                Remove connection
              </button>
            </div>
          )}
        </EdgeLabelRenderer>
      </>
    );
  }
);

InsertableEdge.displayName = 'InsertableEdge';
