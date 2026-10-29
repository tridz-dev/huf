import { useRef, type KeyboardEvent, type PointerEvent } from 'react';
import { PANEL_MAX, PANEL_MIN } from '@/lib/ui/responsive';

interface StepPanelResizerProps {
  width: number;
  onResize: (width: number) => void;
  /** The drag or key press is over: remember the width. */
  onResizeEnd: () => void;
}

/** A thin grab bar on the step panel's left edge: drag it, or focus it and use the arrow keys, to make the panel 300 to 480px wide. */
export function StepPanelResizer({ width, onResize, onResizeEnd }: StepPanelResizerProps) {
  const start = useRef<{ x: number; width: number } | null>(null);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    start.current = { x: event.clientX, width };
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (start.current) onResize(start.current.width + (start.current.x - event.clientX));
  };
  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    if (!start.current) return;
    start.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
    onResizeEnd();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 40 : 10;
    if (event.key === 'ArrowLeft') onResize(width + step);
    else if (event.key === 'ArrowRight') onResize(width - step);
    else if (event.key === 'Home') onResize(PANEL_MIN);
    else if (event.key === 'End') onResize(PANEL_MAX);
    else return;
    event.preventDefault();
    onResizeEnd();
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the step panel"
      aria-valuemin={PANEL_MIN}
      aria-valuemax={PANEL_MAX}
      aria-valuenow={width}
      tabIndex={0}
      data-testid="flow-panel-resizer"
      className="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize touch-none select-none transition-colors hover:bg-signal/40 focus-visible:bg-signal/60 focus-visible:outline-none"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onKeyDown={onKeyDown}
    />
  );
}
