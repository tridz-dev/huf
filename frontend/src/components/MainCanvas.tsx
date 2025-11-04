import { useState, useRef, useEffect } from 'react';
import { Plus, Minus, Maximize2, Play, FileText, PanelLeftOpen, PanelRightOpen } from 'lucide-react';
import { Button } from './ui/button';
import { FlowNode } from './FlowNode';

interface MainCanvasProps {
  showLeftSidebar: boolean;
  showRightSidebar: boolean;
  onToggleLeftSidebar: () => void;
  onToggleRightSidebar: () => void;
}

export function MainCanvas({ showLeftSidebar, showRightSidebar, onToggleLeftSidebar, onToggleRightSidebar }: MainCanvasProps) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const canvasRef = useRef<HTMLDivElement>(null);

  const handleWheel = (e: WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const delta = -e.deltaY * 0.001;
      setZoom((prev) => Math.min(Math.max(0.5, prev + delta), 2));
    }
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 1 || (e.button === 0 && e.target === canvasRef.current)) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setPan({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas) {
      canvas.addEventListener('wheel', handleWheel, { passive: false });
      return () => canvas.removeEventListener('wheel', handleWheel);
    }
  }, []);

  const toggleFullScreen = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    if (showLeftSidebar || showRightSidebar) {
      onToggleLeftSidebar();
      onToggleRightSidebar();
    } else {
      onToggleLeftSidebar();
      onToggleRightSidebar();
    }
  };

  return (
    <>
      <div
        ref={canvasRef}
        className="flex-1 relative overflow-hidden cursor-grab active:cursor-grabbing bg-background"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{
          backgroundImage: `radial-gradient(circle, oklch(var(--muted-foreground) / 0.15) 1px, transparent 1px)`,
          backgroundSize: `${20 * zoom}px ${20 * zoom}px`,
          backgroundPosition: `${pan.x}px ${pan.y}px`,
        }}
      >
        <div
          className="absolute inset-0 flex items-start justify-center pt-20"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transformOrigin: 'center top',
          }}
        >
          <div className="flex flex-col items-center">
            <FlowNode
              icon={<FileText className="w-5 h-5" />}
              title="Web Form"
              subtitle="Trigger"
              variant="primary"
            />
            <FlowNode
              icon={<Play className="w-5 h-5" />}
              title="Run Agent"
              subtitle="Action"
            />
            <FlowNode
              icon={<FileText className="w-5 h-5" />}
              title="End"
              subtitle="Complete"
              variant="success"
              showLine={false}
            />
          </div>
        </div>

        <div className="absolute bottom-4 left-4 flex items-center gap-2 bg-card border border-border rounded-lg shadow-lg p-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setZoom((prev) => Math.max(0.5, prev - 0.1))}
          >
            <Minus className="w-4 h-4" />
          </Button>
          <span className="text-xs font-medium px-2 min-w-[3rem] text-center">
            {Math.round(zoom * 100)}%
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setZoom((prev) => Math.min(2, prev + 0.1))}
          >
            <Plus className="w-4 h-4" />
          </Button>
          <div className="w-px h-6 bg-border mx-1" />
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={toggleFullScreen}
          >
            <Maximize2 className="w-4 h-4" />
          </Button>
        </div>

        {!showLeftSidebar && (
          <Button
            variant="outline"
            size="icon"
            className="absolute bottom-4 left-4 h-10 w-10 rounded-full bg-background/60 backdrop-blur-sm border-muted-foreground/30 hover:bg-background/80 hover:border-muted-foreground/50 transition-all"
            onClick={onToggleLeftSidebar}
          >
            <PanelLeftOpen className="w-4 h-4 text-muted-foreground" />
          </Button>
        )}

        {!showRightSidebar && (
          <Button
            variant="outline"
            size="icon"
            className="absolute bottom-4 right-4 h-10 w-10 rounded-full bg-background/60 backdrop-blur-sm border-muted-foreground/30 hover:bg-background/80 hover:border-muted-foreground/50 transition-all"
            onClick={onToggleRightSidebar}
          >
            <PanelRightOpen className="w-4 h-4 text-muted-foreground" />
          </Button>
        )}
      </div>
    </>
  );
}
