import { memo, useState } from 'react';
import { BaseEdge, EdgeLabelRenderer, EdgeProps, getBezierPath } from 'reactflow';
import { Plus } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface InsertableEdgeData {
  /** The node id a newly inserted action should be attached after (the edge's source). */
  sourceNodeId: string;
  onInsertNode?: (sourceNodeId: string) => void;
}

/**
 * Edge between two real, already-connected nodes. Renders like a normal
 * edge at rest; on hover (or focus) it reveals a small "+" button at the
 * midpoint that inserts a new action node between the two endpoints,
 * reusing the same insertion logic as the trailing "Add step" ghost card
 * (`onAddNode`/`handleSelectAction` re-parents the downstream edge).
 */
export const InsertableEdge = memo(
  ({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, markerEnd, data }: EdgeProps<InsertableEdgeData>) => {
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
        <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
        {/* Wider, invisible hit area so the hover affordance is easy to reach. */}
        <path
          d={edgePath}
          fill="none"
          stroke="transparent"
          strokeWidth={20}
          className="cursor-pointer"
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          onClick={(e) => {
            e.stopPropagation();
            data?.onInsertNode?.(data.sourceNodeId);
          }}
        />
        <EdgeLabelRenderer>
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
              onClick={(e) => {
                e.stopPropagation();
                data?.onInsertNode?.(data.sourceNodeId);
              }}
              className={cn(
                'flex items-center justify-center w-5 h-5 rounded-full border border-line bg-panel text-muted-foreground shadow-sm transition-all duration-150',
                'hover:border-steel-soft hover:text-ink hover:scale-110',
                hovered ? 'opacity-100 scale-100' : 'opacity-0 scale-75 pointer-events-none'
              )}
            >
              <Plus className="w-3 h-3" />
            </button>
          </div>
        </EdgeLabelRenderer>
      </>
    );
  }
);

InsertableEdge.displayName = 'InsertableEdge';
